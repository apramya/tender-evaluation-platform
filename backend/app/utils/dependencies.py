"""
FastAPI dependencies
"""
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import AuthService
from app.models.database import User

logger = logging.getLogger(__name__)

# Global references - will be set by main.py
_db_session = None
_redis_client = None

security = HTTPBearer()


def set_db_session(db_session):
    """Set the database session factory"""
    global _db_session
    _db_session = db_session


def set_redis_client(redis_client):
    """Set the Redis client"""
    global _redis_client
    _redis_client = redis_client


async def get_db() -> AsyncSession:
    """
    Dependency to get database session
    """
    if _db_session is None:
        raise RuntimeError("Database session not initialized")
    
    async with _db_session() as session:
        yield session


async def get_redis():
    """
    Dependency to get Redis client
    """
    return _redis_client


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency to get current authenticated user
    """
    token = credentials.credentials
    
    # Verify token
    payload = AuthService.verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain user ID",
        )
    
    # Get user from database
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    
    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to ensure current user is admin
    """
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    
    return current_user


async def get_review_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to ensure current user can perform manual review.
    """
    allowed_roles = ["procurement_officer", "admin"]
    if current_user.role.value not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Procurement officer or admin access required",
        )
    
    return current_user


async def get_procurement_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to ensure current user can use procurement workflows.
    """
    allowed_roles = ["user", "procurement_officer", "admin"]
    if current_user.role.value not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User, procurement officer, or admin access required",
        )

    return current_user
