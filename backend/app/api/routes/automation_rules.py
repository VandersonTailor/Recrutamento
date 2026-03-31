import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.models.stage_automation_rule import StageAutomationRule
from app.services.audit import AuditService


router = APIRouter()


class RuleCreate(BaseModel):
    job_id: int | None = None
    from_stage: str | None = Field(default=None, max_length=40)
    to_stage: str = Field(max_length=40)
    channel: str = Field(default="whatsapp", max_length=20)
    template_name: str = Field(max_length=120)
    delay_minutes: int = 0
    enabled: bool = True
    variables: dict = Field(default_factory=dict)
    created_by: str | None = Field(default=None, max_length=120)


@router.get("")
def list_rules(
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    return list(db.execute(select(StageAutomationRule).order_by(StageAutomationRule.created_at.desc())).scalars().all())


@router.post("")
def create_rule(
    payload: RuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    row = StageAutomationRule(
        job_id=payload.job_id,
        from_stage=payload.from_stage,
        to_stage=payload.to_stage,
        channel=payload.channel,
        template_name=payload.template_name,
        delay_minutes=max(0, int(payload.delay_minutes)),
        enabled=1 if payload.enabled else 0,
        variables_json=json.dumps(payload.variables or {}, ensure_ascii=False),
        created_by=payload.created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    AuditService(db).log(
        action="automation_rules.create",
        resource_type="automation_rule",
        resource_id=str(row.id),
        ip=request.client.host if request.client else None,
        metadata={"to_stage": row.to_stage, "template_name": row.template_name},
    )
    return row
