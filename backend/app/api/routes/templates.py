from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.models.message_template import MessageTemplate
from app.repositories.templates import TemplateRepository
from app.schemas.template import (
    RenderTemplateRequest,
    RenderTemplateResponse,
    TemplateApproveRequest,
    TemplateCreate,
    TemplateOut,
)
from app.services.audit import AuditService


router = APIRouter()


@router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    repo = TemplateRepository(db)
    return repo.list()


@router.post("", response_model=TemplateOut)
def create_template(
    payload: TemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    repo = TemplateRepository(db)
    next_version = repo.latest_version(channel=payload.channel, name=payload.name) + 1
    tpl = MessageTemplate(
        channel=payload.channel,
        name=payload.name,
        version=next_version,
        status="draft",
        parent_id=payload.parent_id,
        subject=payload.subject,
        body=payload.body,
    )
    created = repo.create(tpl)
    AuditService(db).log(
        action="templates.create",
        resource_type="message_template",
        resource_id=str(created.id),
        ip=request.client.host if request.client else None,
        metadata={"name": created.name, "version": created.version, "status": created.status},
        actor=payload.created_by or "anonymous",
    )
    return created


@router.post("/{template_id}/approve", response_model=TemplateOut)
def approve_template(
    template_id: int,
    payload: TemplateApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    tpl = db.get(MessageTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    tpl.status = "approved"
    tpl.approved_by = payload.approved_by
    tpl.approved_at = datetime.utcnow()
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    AuditService(db).log(
        action="templates.approve",
        resource_type="message_template",
        resource_id=str(template_id),
        ip=request.client.host if request.client else None,
        metadata={"name": tpl.name, "version": tpl.version},
        actor=payload.approved_by or "anonymous",
    )
    return tpl


@router.post("/render", response_model=RenderTemplateResponse)
def render(payload: RenderTemplateRequest):
    subject = _safe_format(payload.subject, payload.variables) if payload.subject else None
    body = _safe_format(payload.body, payload.variables)
    return {"subject": subject, "body": body}


def _safe_format(template: str, variables: dict) -> str:
    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return template.format_map(_SafeDict(**(variables or {})))
