"""
Authentication API routes
"""
import logging
import secrets
from datetime import datetime
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.models.database import EmailVerificationCode, User, UserRole
from app.schemas.schemas import (
    TokenResponse,
    UserAdminCreate,
    UserAdminUpdate,
    UserCreate,
    UserLogin,
    UserResponse,
    UserSignupOtpRequest,
    UserSignupOtpVerify,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.services.oauth_service import OAuthService
from app.utils.config import settings
from app.utils.dependencies import get_admin_user, get_db, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_USER_ROLES = {
    UserRole.USER.value,
    UserRole.PROCUREMENT_OFFICER.value,
    UserRole.ADMIN.value,
}


def _frontend_redirect(path: str, params: dict) -> RedirectResponse:
    return RedirectResponse(f"{settings.FRONTEND_URL}{path}?{urlencode(params)}")


def _validate_public_signup_email(email: str, is_first_user: bool) -> None:
    if is_first_user:
        return
    if not settings.ALLOW_PUBLIC_SIGNUP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public signup is disabled. Ask an administrator to create your account.",
        )

    normalized = email.lower()
    domain = normalized.split("@")[-1]
    blocked_emails = [item.lower() for item in settings.PUBLIC_SIGNUP_BLOCKED_EMAILS]
    blocked_domains = [item.lower().lstrip("@") for item in settings.PUBLIC_SIGNUP_BLOCKED_DOMAINS]
    if normalized in blocked_emails or domain in blocked_domains:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This email is not allowed for signup.")

    allowed_emails = [item.lower() for item in settings.PUBLIC_SIGNUP_ALLOWED_EMAILS]
    allowed_domains = [item.lower().lstrip("@") for item in settings.PUBLIC_SIGNUP_ALLOWED_DOMAINS]
    if allowed_emails or allowed_domains:
        if normalized not in allowed_emails and domain not in allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This email is not approved for signup. Ask an administrator to add it.",
            )


async def _is_first_user(db: AsyncSession) -> bool:
    user_count_result = await db.execute(select(func.count(User.id)))
    return (user_count_result.scalar() or 0) == 0


def _token_response(user: User) -> TokenResponse:
    access_token = AuthService.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )


@router.post("/signup/request-otp")
async def request_signup_otp(
    user_data: UserSignupOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    is_first_user = await _is_first_user(db)
    _validate_public_signup_email(user_data.email, is_first_user)

    existing = await db.execute(select(User).where(User.email == user_data.email))
    if existing.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    otp = "".join(secrets.choice("0123456789") for _ in range(settings.EMAIL_OTP_LENGTH))
    verification = EmailVerificationCode(
        id=secrets.token_urlsafe(24),
        email=user_data.email.lower(),
        code_hash=AuthService.hash_password(otp),
        full_name=user_data.full_name.strip(),
        organization=user_data.organization,
        password_hash=AuthService.hash_password(user_data.password),
        expires_at=datetime.utcnow() + timedelta(minutes=settings.EMAIL_OTP_EXPIRE_MINUTES),
    )
    db.add(verification)
    await db.commit()

    try:
        EmailService.send_signup_otp(user_data.email, otp)
    except Exception as e:
        logger.error(f"Could not send signup OTP to {user_data.email}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not send verification email")

    return {"message": "Verification code sent"}


@router.post("/signup/verify", response_model=TokenResponse)
async def verify_signup_otp(
    payload: UserSignupOtpVerify,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.email == payload.email.lower(),
            EmailVerificationCode.consumed == False,  # noqa: E712
        )
        .order_by(EmailVerificationCode.created_at.desc())
    )
    verification = result.scalars().first()
    if not verification or verification.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired or not found")

    verification.attempts = (verification.attempts or 0) + 1
    if verification.attempts > 5:
        verification.consumed = True
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many incorrect verification attempts")

    if not AuthService.verify_password(payload.otp, verification.code_hash):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    existing = await db.execute(select(User).where(User.email == verification.email))
    if existing.scalars().first():
        verification.consumed = True
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    user = User(
        id=secrets.token_urlsafe(24),
        email=verification.email,
        full_name=verification.full_name,
        hashed_password=verification.password_hash,
        role=UserRole.ADMIN if await _is_first_user(db) else UserRole.USER,
        organization=verification.organization,
        is_active=True,
    )
    verification.consumed = True
    db.add(user)
    AuditService.add_log(
        db,
        user=user,
        action="signup",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role.value, "email_verified": True},
    )
    await db.commit()
    await db.refresh(user)
    return _token_response(user)


@router.post("/signup", response_model=TokenResponse)
async def signup(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user
    """
    try:
        is_first_user = await _is_first_user(db)
        _validate_public_signup_email(user_data.email, is_first_user)

        # Register user
        user = await AuthService.register_user(db, user_data)
        AuditService.add_log(
            db,
            user=user,
            action="signup",
            entity_type="user",
            entity_id=user.id,
            details={"role": user.role.value},
        )
        await db.commit()
        
        # Create access token
        access_token = AuthService.create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )
        
        logger.info(f"User registered successfully: {user.email}")
        
        return TokenResponse(
            access_token=access_token,
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user",
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Login with email and password
    """
    try:
        # Authenticate user
        user = await AuthService.authenticate_user(
            db,
            credentials.email,
            credentials.password,
        )
        
        if not user:
            logger.warning(f"Failed login attempt for email: {credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        
        # Create access token
        access_token = AuthService.create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )
        
        logger.info(f"User logged in: {user.email}")
        AuditService.add_log(
            db,
            user=user,
            action="login",
            entity_type="user",
            entity_id=user.id,
            details={"method": "password"},
        )
        await db.commit()
        
        return TokenResponse(
            access_token=access_token,
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed",
        )


@router.get("/oauth/{provider}/start")
async def start_oauth(provider: str):
    """
    Start a Google or LinkedIn OAuth login.
    """
    try:
        OAuthService.ensure_provider_configured(provider)
        state = OAuthService.create_state(provider)
        return RedirectResponse(OAuthService.authorization_url(provider, state))
    except ValueError as e:
        return _frontend_redirect("/login", {"oauth_error": str(e)})


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete OAuth login and redirect back to the React app with an app JWT.
    """
    if error:
        return _frontend_redirect("/login", {"oauth_error": error})

    if not code or not state or not OAuthService.verify_state(state, provider):
        return _frontend_redirect("/login", {"oauth_error": "Invalid OAuth response"})

    try:
        OAuthService.ensure_provider_configured(provider)
        userinfo = await OAuthService.fetch_userinfo(provider, code)
        profile = OAuthService.normalize_userinfo(provider, userinfo)
        user = await AuthService.get_or_create_oauth_user(
            db,
            email=profile["email"],
            full_name=profile["full_name"],
        )
        AuditService.add_log(
            db,
            user=user,
            action="login",
            entity_type="user",
            entity_id=user.id,
            details={"method": provider},
        )
        await db.commit()

        access_token = AuthService.create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )

        return _frontend_redirect(
            "/oauth/callback",
            {
                "token": access_token,
                "user_id": user.id,
                "email": user.email,
                "role": user.role.value,
                "full_name": user.full_name,
            },
        )
    except (ValueError, httpx.HTTPError) as e:
        logger.error(f"OAuth callback failed for {provider}: {e}")
        return _frontend_redirect("/login", {"oauth_error": "OAuth login failed"})
    except Exception as e:
        logger.error(f"Unexpected OAuth error for {provider}: {e}")
        return _frontend_redirect("/login", {"oauth_error": "OAuth login failed"})


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user = Depends(get_current_user),
):
    """
    Get current logged-in user information
    """
    return UserResponse.model_validate(current_user)


@router.get("/users")
async def list_users(
    current_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """
    List users for admin role management.
    """
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    users = result.scalars().all()
    return {
        "total": len(users),
        "users": [UserResponse.model_validate(user) for user in users],
    }


@router.post("/users", response_model=UserResponse)
async def create_user_admin(
    user_data: UserAdminCreate,
    current_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a user with a selected role. Admin only.
    """
    existing = await db.execute(select(User).where(User.email == user_data.email))
    if existing.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    try:
        role = UserRole(user_data.role)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    if role.value not in SUPPORTED_USER_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    import uuid
    user = User(
        id=str(uuid.uuid4()),
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=AuthService.hash_password(user_data.password),
        role=role,
        organization=user_data.organization,
        is_active=user_data.is_active,
    )
    db.add(user)
    AuditService.add_log(
        db,
        user=current_user,
        action="create_user",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role.value, "email": user.email},
    )
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_admin(
    user_id: str,
    update_data: UserAdminUpdate,
    current_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a user's profile, credentials, role, or active status. Admin only.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if update_data.email is not None and update_data.email != user.email:
        existing = await db.execute(select(User).where(User.email == update_data.email))
        if existing.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already used")
        user.email = update_data.email

    if update_data.full_name is not None:
        if not update_data.full_name.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Full name is required")
        user.full_name = update_data.full_name.strip()

    if update_data.organization is not None:
        user.organization = update_data.organization.strip() or None

    if update_data.password is not None:
        user.hashed_password = AuthService.hash_password(update_data.password)

    if update_data.role is not None:
        try:
            if user.id == current_user.id and update_data.role != UserRole.ADMIN.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot remove your own admin role",
                )
            role = UserRole(update_data.role)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
        if role.value not in SUPPORTED_USER_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
        user.role = role

    if update_data.is_active is not None:
        if user.id == current_user.id and not update_data.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account",
            )
        user.is_active = update_data.is_active

    AuditService.add_log(
        db,
        user=current_user,
        action="update_user",
        entity_type="user",
        entity_id=user.id,
        details={
            "email": user.email,
            "full_name": user.full_name,
            "organization": user.organization,
            "role": user.role.value,
            "is_active": user.is_active,
            "password_changed": update_data.password is not None,
        },
    )
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}")
async def delete_user_admin(
    user_id: str,
    current_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete a user account while preserving audit/review history.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")

    deleted_at = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    original_email = user.email
    user.email = f"deleted-{deleted_at}-{user.id[:8]}@deleted.local"
    user.full_name = f"Deleted user {user.id[:8]}"
    user.organization = None
    user.is_active = False
    user.hashed_password = AuthService.hash_password(f"deleted-{user.id}-{deleted_at}")

    AuditService.add_log(
        db,
        user=current_user,
        action="delete_user",
        entity_type="user",
        entity_id=user.id,
        details={"original_email": original_email, "soft_deleted": True},
    )
    await db.commit()
    return {"message": "User deleted", "user_id": user.id}


@router.get("/verify-token", response_model=dict)
async def verify_token(
    token: str,
):
    """
    Verify if a JWT token is valid
    """
    payload = AuthService.verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    
    return {
        "valid": True,
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role"),
    }
