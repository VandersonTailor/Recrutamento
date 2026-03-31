from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.models.processing_log import ProcessingLog
from app.schemas.processing_log import ProcessingLogOut
from app.services.audit import AuditService


router = APIRouter()


@router.get("", response_model=list[ProcessingLogOut])
def list_processing_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    rows = list(db.execute(select(ProcessingLog).order_by(ProcessingLog.created_at.desc()).limit(limit)).scalars().all())
    AuditService(db).log(action="processing_logs.list", ip=request.client.host if request.client else None, metadata={"count": len(rows)})
    return rows
