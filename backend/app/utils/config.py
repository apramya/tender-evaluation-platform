"""
Application configuration and settings
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import ClassVar, List
import os


def _csv_env(name: str, defaults: List[str]) -> List[str]:
    value = os.getenv(name, "")
    if not value:
        return defaults
    return [item.strip() for item in value.split(",") if item.strip()]


def _database_url(value: str) -> str:
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql://", 1)
    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # App
    APP_NAME: str = "Tender Evaluation Platform"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    API_VERSION: str = "1.0.0"
    
    # Server
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    ALLOWED_ORIGINS: ClassVar[List[str]] = _csv_env(
        "ALLOWED_ORIGINS",
        [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            os.getenv("FRONTEND_URL", "http://localhost:3000"),
        ],
    )
    AUTO_CREATE_TABLES: bool = os.getenv("AUTO_CREATE_TABLES", os.getenv("DEBUG", "False")).lower() == "true"
    ALLOW_PUBLIC_SIGNUP: bool = os.getenv("ALLOW_PUBLIC_SIGNUP", "false").lower() == "true"
    PUBLIC_SIGNUP_ALLOWED_EMAILS: ClassVar[List[str]] = _csv_env("PUBLIC_SIGNUP_ALLOWED_EMAILS", [])
    PUBLIC_SIGNUP_ALLOWED_DOMAINS: ClassVar[List[str]] = _csv_env("PUBLIC_SIGNUP_ALLOWED_DOMAINS", [])
    PUBLIC_SIGNUP_BLOCKED_EMAILS: ClassVar[List[str]] = _csv_env("PUBLIC_SIGNUP_BLOCKED_EMAILS", [])
    PUBLIC_SIGNUP_BLOCKED_DOMAINS: ClassVar[List[str]] = _csv_env("PUBLIC_SIGNUP_BLOCKED_DOMAINS", [])
    EMAIL_OTP_EXPIRE_MINUTES: int = int(os.getenv("EMAIL_OTP_EXPIRE_MINUTES", "10"))
    EMAIL_OTP_LENGTH: int = int(os.getenv("EMAIL_OTP_LENGTH", "6"))
    
    # Database
    DATABASE_URL: str = _database_url(os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://tender_user:tender_password@localhost:5432/tender_db"
    ))

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        return _database_url(value)
    
    # Redis
    REDIS_URL: str = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0"
    )
    
    # JWT
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "your-secret-key-change-in-production"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))

    # OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        os.getenv("GOOGLE_CALLBACK_URL", "http://localhost:8000/api/auth/oauth/google/callback"),
    )
    LINKEDIN_CLIENT_ID: str = os.getenv("LINKEDIN_CLIENT_ID", "")
    LINKEDIN_CLIENT_SECRET: str = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    LINKEDIN_REDIRECT_URI: str = os.getenv(
        "LINKEDIN_REDIRECT_URI",
        os.getenv("LINKEDIN_CALLBACK_URL", "http://localhost:8000/api/auth/oauth/linkedin/callback"),
    )
    
    # Groq
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile"))
    
    # Document Processing
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_FILE_TYPES: List[str] = ["pdf", "docx", "doc", "txt", "png", "jpg", "jpeg"]
    
    # OCR
    USE_TESSERACT: bool = os.getenv("USE_TESSERACT", "True").lower() == "true"
    TESSERACT_PATH: str = os.getenv("TESSERACT_PATH", "/usr/bin/tesseract")
    
    # Vector Database
    CHROMA_PERSIST_DIR: str = os.getenv(
        "CHROMA_PERSIST_DIR",
        "./chroma_db"
    )
    EMBEDDINGS_MODEL: str = os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    VECTOR_SEARCH_ENABLED: bool = os.getenv("VECTOR_SEARCH_ENABLED", "true").lower() == "true"
    
    # Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 100
    PROCESS_UPLOADS_ON_REQUEST: bool = os.getenv("PROCESS_UPLOADS_ON_REQUEST", "false").lower() == "true"
    
    # Email (for notifications)
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "noreply@tenderevaluation.com")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", os.getenv("SMTP_PASS", ""))
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    
    # Confidence Thresholds
    MIN_CONFIDENCE_FOR_AUTO_DECISION: float = 0.85
    CONFIDENCE_THRESHOLD_MANUAL_REVIEW: float = 0.70
    
    # File Storage
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    TEMP_DIR: str = os.getenv("TEMP_DIR", "./temp")

    # Object Storage (optional)
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")  # local or s3
    S3_UPLOAD_ON_REQUEST: bool = os.getenv("S3_UPLOAD_ON_REQUEST", "false").lower() == "true"
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
    S3_PREFIX: str = os.getenv("S3_PREFIX", "tender-evaluation")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
