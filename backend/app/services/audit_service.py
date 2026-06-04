"""
Audit logging helpers.
"""
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AuditLog, User


class AuditService:
    """Create audit log rows for compliance-sensitive actions."""

    @staticmethod
    def add_log(
        db: AsyncSession,
        *,
        user: Optional[User],
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        tender_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        log = AuditLog(
            id=str(uuid.uuid4()),
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            tender_id=tender_id,
            details=details or {},
            status=status,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(log)
        return log
