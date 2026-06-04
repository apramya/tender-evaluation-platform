"""
Authentication service for user management
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.database import User, UserRole
from app.schemas.schemas import UserCreate, TokenResponse
from app.utils.config import settings

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication and user management"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def create_access_token(
        user_id: str,
        email: str,
        role: str,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token"""
        if expires_delta is None:
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        expire = datetime.now(timezone.utc) + expires_delta
        
        to_encode = {
            "sub": user_id,
            "email": email,
            "role": role,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid token")
            return None
    
    @staticmethod
    async def register_user(
        session: AsyncSession,
        user_data: UserCreate,
    ) -> User:
        """Register a new user"""
        # Check if user already exists
        result = await session.execute(
            select(User).where(User.email == user_data.email)
        )
        if result.scalars().first():
            raise ValueError(f"User with email {user_data.email} already exists")

        user_count_result = await session.execute(select(func.count(User.id)))
        is_first_user = (user_count_result.scalar() or 0) == 0
        
        # Create new user
        user = User(
            id=str(uuid.uuid4()),
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=AuthService.hash_password(user_data.password),
            role=UserRole.ADMIN if is_first_user else UserRole.USER,
            organization=user_data.organization,
        )
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"New user registered: {user.email}")
        return user

    @staticmethod
    async def get_or_create_oauth_user(
        session: AsyncSession,
        email: str,
        full_name: str,
    ) -> User:
        """Find an existing local user by email or create one for OAuth login."""
        result = await session.execute(select(User).where(User.email == email))
        existing_user = result.scalars().first()
        if existing_user:
            if not existing_user.is_active:
                raise ValueError("This account is inactive")
            return existing_user

        user_count_result = await session.execute(select(func.count(User.id)))
        is_first_user = (user_count_result.scalar() or 0) == 0

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=full_name,
            hashed_password=AuthService.hash_password(str(uuid.uuid4())),
            role=UserRole.ADMIN if is_first_user else UserRole.USER,
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        logger.info(f"New OAuth user registered: {user.email}")
        return user
    
    @staticmethod
    async def authenticate_user(
        session: AsyncSession,
        email: str,
        password: str,
    ) -> Optional[User]:
        """Authenticate user with email and password"""
        result = await session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalars().first()
        
        if not user:
            return None
        
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        
        if not user.is_active:
            return None
        
        return user
    
    @staticmethod
    async def get_user_by_id(
        session: AsyncSession,
        user_id: str,
    ) -> Optional[User]:
        """Get user by ID"""
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalars().first()
    
    @staticmethod
    async def get_user_by_email(
        session: AsyncSession,
        email: str,
    ) -> Optional[User]:
        """Get user by email"""
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()
