from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogOut
from app.services.audit import AuditService


router = APIRouter()


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    request: Request,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = list(db.execute(stmt).scalars().all())
    AuditService(db).log(action="audit.list", ip=request.client.host if request.client else None, metadata={"action": action, "limit": limit})
    return rows
