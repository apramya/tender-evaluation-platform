"""
Create or repair development demo users without touching tender/sample data.
Run inside backend container:
python -m scripts.ensure_demo_users
"""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, User, UserRole
from app.services.auth_service import AuthService
from app.utils.config import settings


DEMO_USERS = [
    ("admin@tenderevaluation.com", "admin123", "Admin User", UserRole.ADMIN, "Government"),
    ("officer@tenderevaluation.com", "officer123", "Procurement Officer", UserRole.PROCUREMENT_OFFICER, "Ministry of Roads"),
    ("user@tenderevaluation.com", "user12345", "Project User", UserRole.USER, "Client Team"),
]


async def main():
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        for email, password, full_name, role, organization in DEMO_USERS:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            if user:
                user.full_name = full_name
                user.hashed_password = AuthService.hash_password(password)
                user.role = role
                user.organization = organization
                user.is_active = True
                print(f"repaired {email}")
            else:
                session.add(User(
                    id=str(uuid.uuid4()),
                    email=email,
                    full_name=full_name,
                    hashed_password=AuthService.hash_password(password),
                    role=role,
                    organization=organization,
                    is_active=True,
                ))
                print(f"created {email}")
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
