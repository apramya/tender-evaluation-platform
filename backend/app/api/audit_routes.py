"""
Audit API routes
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.database import AuditLog
from app.schemas.schemas import AuditLogResponse
from app.utils.dependencies import get_db, get_current_user, get_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_audit_logs(
    current_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """
    List audit logs (admin only)
    """
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    )
    logs = result.scalars().all()
    
    return {
        "total": len(logs),
        "logs": logs,
    }


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: str,
    current_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get specific audit log
    """
    result = await db.execute(
        select(AuditLog).where(AuditLog.id == log_id)
    )
    log = result.scalars().first()
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )
    
    return log


@router.get("/tender/{tender_id}")
async def get_tender_audit_logs(
    tender_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get audit logs for a specific tender
    """
    result = await db.execute(
        select(AuditLog).where(AuditLog.tender_id == tender_id)
    )
    logs = result.scalars().all()
    
    return {
        "tender_id": tender_id,
        "total": len(logs),
        "logs": logs,
    }
