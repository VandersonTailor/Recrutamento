from fastapi import APIRouter, Depends, Query, Request
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.models.dead_letter_event import DeadLetterEvent
from app.services.alerts import collect_active_alerts
from app.services.audit import AuditService
from app.services.dead_letter import DeadLetterService


router = APIRouter()


@router.get("/alerts")
def get_active_alerts(
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    return {"generated_at": datetime.utcnow().isoformat(), "alerts": collect_active_alerts(db)}


@router.get("/dead-letter")
def list_dead_letter(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    return DeadLetterService(db).list(status=status, limit=limit)


@router.post("/dead-letter/{dlq_id}/reprocess")
def reprocess_dead_letter(
    dlq_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    result = DeadLetterService(db).reprocess_communication(dlq_id=dlq_id)
    AuditService(db).log(
        action="dlq.reprocess",
        resource_type="dead_letter",
        resource_id=str(dlq_id),
        ip=request.client.host if request.client else None,
        metadata=result,
    )
    return result


@router.get("/dead-letter/stats")
def dead_letter_stats(
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    rows = db.execute(select(DeadLetterEvent.status, func.count(DeadLetterEvent.id)).group_by(DeadLetterEvent.status)).all()
    out: dict[str, int] = {}
    for status, count in rows:
        out[str(status)] = int(count)
    return out
