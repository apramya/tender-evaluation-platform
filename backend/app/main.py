"""
Tender Evaluation Platform - Main FastAPI Application
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import redis.asyncio as redis

from app.utils.dependencies import set_db_session, set_redis_client

from app.api import (
    auth_routes,
    tender_routes,
    bidder_routes,
    evaluation_routes,
    audit_routes,
    review_routes,
    export_routes,
)
from app.models.database import Base
from app.utils.config import settings
from app.utils.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

if settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment="production" if not settings.DEBUG else "development",
    )

# Global database and cache objects
engine = None
AsyncSessionLocal = None
redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown
    """
    global engine, AsyncSessionLocal, redis_client
    
    # Startup
    logger.info("Starting Tender Evaluation Platform...")
    print("DATABASE_URL =", settings.DATABASE_URL)
    
    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=40,
    )
    
    # Create session factory
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    set_db_session(AsyncSessionLocal)
    
    # Development convenience only. Production should run Alembic migrations.
    if settings.AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            if settings.DATABASE_URL.startswith("postgresql"):
                await conn.execute(text("""
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
                            ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'USER';
                        END IF;
                    END
                    $$;
                """))
            await conn.run_sync(Base.metadata.create_all)
    
    # Initialize Redis
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL, encoding="utf8", decode_responses=True
        )
        set_redis_client(redis_client)
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        redis_client = None
   
    logger.info("✓ Application startup complete")
    yield
    
    # Shutdown
    logger.info("Shutting down Tender Evaluation Platform...")
    
    if redis_client:
        await redis_client.close()
    
    await engine.dispose()
    logger.info("✓ Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Tender Evaluation & Eligibility Analysis Platform",
    description="AI-powered government procurement tender analysis system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])
app.include_router(tender_routes.router, prefix="/api/tenders", tags=["tenders"])
app.include_router(bidder_routes.router, prefix="/api/bidders", tags=["bidders"])
app.include_router(
    evaluation_routes.router, prefix="/api/evaluations", tags=["evaluations"]
)
app.include_router(audit_routes.router, prefix="/api/audit", tags=["audit"])
app.include_router(review_routes.router, prefix="/api/review", tags=["review"])
app.include_router(export_routes.router, prefix="/api/export", tags=["export"])


@app.get("/", tags=["health"])
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Tender Evaluation Platform",
        "version": "1.0.0",
    }


@app.get("/api/health", tags=["health"])
async def health_check():
    """Detailed health check endpoint"""
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "redis": "unknown",
    }
    
    # Check database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        health_status["database"] = "ok"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Redis
    try:
        if redis_client:
            await redis_client.ping()
            health_status["redis"] = "ok"
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status


def get_db():
    """Dependency for getting database session"""
    return AsyncSessionLocal


def get_redis():
    """Dependency for getting Redis client"""
    return redis_client


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
