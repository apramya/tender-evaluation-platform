"""
OAuth helpers for Google and LinkedIn sign-in.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from urllib.parse import urlencode

import httpx
import jwt

from app.utils.config import settings

logger = logging.getLogger(__name__)


class OAuthService:
    """Provider-specific OAuth/OpenID Connect flow helpers."""

    PROVIDERS: Dict[str, Dict[str, str]] = {
        "google": {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scope": "openid email profile",
        },
        "linkedin": {
            "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
            "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
            "userinfo_url": "https://api.linkedin.com/v2/userinfo",
            "scope": "openid profile email",
        },
    }

    @staticmethod
    def _client_id(provider: str) -> str:
        return settings.GOOGLE_CLIENT_ID if provider == "google" else settings.LINKEDIN_CLIENT_ID

    @staticmethod
    def _client_secret(provider: str) -> str:
        return settings.GOOGLE_CLIENT_SECRET if provider == "google" else settings.LINKEDIN_CLIENT_SECRET

    @staticmethod
    def redirect_uri(provider: str) -> str:
        return settings.GOOGLE_REDIRECT_URI if provider == "google" else settings.LINKEDIN_REDIRECT_URI

    @classmethod
    def ensure_provider_configured(cls, provider: str) -> None:
        if provider not in cls.PROVIDERS:
            raise ValueError("Unsupported OAuth provider")
        if not cls._client_id(provider) or not cls._client_secret(provider):
            raise ValueError(f"{provider.title()} OAuth is not configured")

    @staticmethod
    def create_state(provider: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "provider": provider,
            "purpose": "oauth_state",
            "iat": now,
            "exp": now + timedelta(minutes=10),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def verify_state(state: str, provider: str) -> bool:
        try:
            payload = jwt.decode(
                state,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            return payload.get("purpose") == "oauth_state" and payload.get("provider") == provider
        except jwt.InvalidTokenError:
            logger.warning("Invalid OAuth state token")
            return False

    @classmethod
    def authorization_url(cls, provider: str, state: str) -> str:
        config = cls.PROVIDERS[provider]
        params = {
            "response_type": "code",
            "client_id": cls._client_id(provider),
            "redirect_uri": cls.redirect_uri(provider),
            "scope": config["scope"],
            "state": state,
        }
        return f"{config['auth_url']}?{urlencode(params)}"

    @classmethod
    async def fetch_userinfo(cls, provider: str, code: str) -> Dict[str, Any]:
        config = cls.PROVIDERS[provider]
        token_payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cls.redirect_uri(provider),
            "client_id": cls._client_id(provider),
            "client_secret": cls._client_secret(provider),
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                config["token_url"],
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise ValueError("OAuth provider did not return an access token")

            user_response = await client.get(
                config["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_response.raise_for_status()
            return user_response.json()

    @staticmethod
    def normalize_userinfo(provider: str, userinfo: Dict[str, Any]) -> Dict[str, Any]:
        email = userinfo.get("email")
        name = userinfo.get("name") or " ".join(
            part for part in [userinfo.get("given_name"), userinfo.get("family_name")] if part
        )
        email_verified = userinfo.get("email_verified")

        if not email:
            raise ValueError(f"{provider.title()} did not return an email address")
        if email_verified is False:
            raise ValueError("OAuth email address is not verified")

        return {
            "email": email.lower(),
            "full_name": name or email.split("@")[0],
        }
