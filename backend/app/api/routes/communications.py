import json
from datetime import datetime, timedelta, timezone
import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import require_roles
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.communication_event import CommunicationEvent
from app.models.job import Job
from app.models.message_template import MessageTemplate
from app.repositories.templates import TemplateRepository
from app.schemas.communication import (
    CommunicationEventOut,
    PendingCommunicationOut,
    ScheduleInterviewRequest,
    SendTemplateRequest,
)
from app.services.audit import AuditService
from app.services.communication_dispatcher import CommunicationDispatcherService


router = APIRouter()


@router.get("/application/{application_id}", response_model=list[CommunicationEventOut])
def list_application_communications(
    application_id: int,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    rows = (
        db.execute(
            select(CommunicationEvent)
            .where(CommunicationEvent.application_id == application_id)
            .order_by(CommunicationEvent.created_at.desc())
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/pending", response_model=PendingCommunicationOut)
def list_pending_communications(
    due_in_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    until = now + timedelta(hours=due_in_hours)
    rows = (
        db.execute(
            select(CommunicationEvent)
            .where(
                CommunicationEvent.status.in_(["planned", "retrying"]),
                CommunicationEvent.scheduled_for.is_not(None),
                (
                    (CommunicationEvent.next_attempt_at.is_not(None) & (CommunicationEvent.next_attempt_at <= until))
                    | (CommunicationEvent.next_attempt_at.is_(None) & (CommunicationEvent.scheduled_for <= until))
                ),
            )
            .order_by(CommunicationEvent.next_attempt_at.asc(), CommunicationEvent.scheduled_for.asc())
        )
        .scalars()
        .all()
    )
    return {"total": len(rows), "items": rows}


@router.get("/panel")
def communication_panel(
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    totals = (
        db.execute(
            select(CommunicationEvent.status, CommunicationEvent.channel, func.count(CommunicationEvent.id))
            .group_by(CommunicationEvent.status, CommunicationEvent.channel)
        )
        .all()
    )
    out = []
    for status, channel, count in totals:
        out.append({"status": status, "channel": channel, "count": int(count)})
    latest = (
        db.execute(
            select(CommunicationEvent)
            .order_by(CommunicationEvent.created_at.desc())
            .limit(30)
        )
        .scalars()
        .all()
    )
    return {"totals": out, "latest": latest}


@router.post("/application/{application_id}/send-template", response_model=CommunicationEventOut)
def send_template(
    application_id: int,
    payload: SendTemplateRequest,
    request: Request,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    if payload.channel != "whatsapp":
        raise HTTPException(status_code=422, detail="Canal inválido. Este módulo aceita apenas WhatsApp (WPPConnect).")
    app, cand, job = _load_application_context(db=db, application_id=application_id)
    template = _find_template(db=db, channel=payload.channel, template_name=payload.template_name)
    merged_vars = _default_variables(app=app, cand=cand, job=job)
    merged_vars.update(payload.variables or {})

    if template:
        subject_template = payload.subject if payload.subject is not None else template.subject
        body_template = payload.body if payload.body is not None else template.body
        template_name = template.name
    else:
        subject_template = payload.subject
        body_template = payload.body
        template_name = payload.template_name

    if not body_template:
        raise HTTPException(status_code=422, detail="Mensagem sem corpo. Informe body ou template_name válido.")

    rendered_subject = _safe_format(subject_template, merged_vars) if subject_template else None
    rendered_body = _safe_format(body_template, merged_vars)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    send_at = payload.send_at.replace(tzinfo=None) if payload.send_at else now
    retry_max = max(1, int(get_settings().communication_dispatch_max_retries or 3))
    message_id = _build_message_id(
        application_id=application_id,
        channel=payload.channel,
        body=rendered_body,
        send_at=send_at,
        idempotency_key=x_idempotency_key,
    )
    existing = db.execute(select(CommunicationEvent).where(CommunicationEvent.message_id == message_id)).scalars().first()
    if existing:
        return existing

    event = CommunicationEvent(
        application_id=application_id,
        channel=payload.channel,
        message_id=message_id,
        event_type="message",
        status="planned",
        template_name=template_name,
        subject=rendered_subject,
        body=rendered_body,
        payload_json=json.dumps({"variables": merged_vars}, ensure_ascii=False),
        scheduled_for=send_at,
        sent_at=None,
        attempts=0,
        max_attempts=retry_max,
        next_attempt_at=send_at,
        error_message=None,
        created_by=payload.created_by,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    AuditService(db).log(
        action="communications.send_template",
        resource_type="application",
        resource_id=str(application_id),
        ip=request.client.host if request.client else None,
        metadata={"channel": payload.channel, "template_name": template_name, "status": "planned"},
    )
    return event


@router.post("/application/{application_id}/schedule-interview", response_model=list[CommunicationEventOut])
def schedule_interview(
    application_id: int,
    payload: ScheduleInterviewRequest,
    request: Request,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    if payload.channel != "whatsapp":
        raise HTTPException(status_code=422, detail="Canal inválido. Este módulo aceita apenas WhatsApp (WPPConnect).")
    app, cand, job = _load_application_context(db=db, application_id=application_id)
    template = _find_template(db=db, channel=payload.channel, template_name=payload.template_name)

    base_vars = _default_variables(app=app, cand=cand, job=job)
    interview_at = payload.interview_at.replace(tzinfo=None)
    base_vars.update(
        {
            "interview_at": interview_at.strftime("%Y-%m-%d %H:%M"),
            "interview_location": payload.location,
            "interview_mode": payload.mode,
            "interviewer": payload.interviewer or "Equipe RH Carris",
            "interview_notes": payload.notes or "",
        }
    )

    subject_template = (
        template.subject
        if template and template.subject
        else "Entrevista agendada - {job_title} - Carris"
    )
    body_template = (
        template.body
        if template
        else (
            "Olá {candidate_name}, sua entrevista para a vaga {job_title} foi agendada para {interview_at} "
            "({interview_mode}) em {interview_location}. Entrevistador(a): {interviewer}. {interview_notes}"
        )
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created: list[CommunicationEvent] = []

    invite_message_id = _build_message_id(
        application_id=application_id,
        channel=payload.channel,
        body=_safe_format(body_template, base_vars),
        send_at=now,
        idempotency_key=f"{x_idempotency_key or ''}-invite",
    )
    existing_invite = db.execute(select(CommunicationEvent).where(CommunicationEvent.message_id == invite_message_id)).scalars().first()
    if existing_invite:
        return [existing_invite]

    invite = CommunicationEvent(
        application_id=application_id,
        channel=payload.channel,
        message_id=invite_message_id,
        event_type="interview_invite",
        status="planned",
        template_name=payload.template_name,
        subject=_safe_format(subject_template, base_vars),
        body=_safe_format(body_template, base_vars),
        payload_json=json.dumps({"variables": base_vars, "kind": "invite"}, ensure_ascii=False),
        scheduled_for=now,
        sent_at=None,
        attempts=0,
        max_attempts=max(1, int(get_settings().communication_dispatch_max_retries or 3)),
        next_attempt_at=now,
        error_message=None,
        created_by=payload.created_by,
    )
    created.append(invite)
    db.add(invite)

    if payload.auto_reminders:
        for hours_before in (24, 2):
            reminder_at = interview_at - timedelta(hours=hours_before)
            if reminder_at <= now:
                continue
            vars_reminder = {**base_vars, "hours_before": hours_before}
            reminder_message_id = _build_message_id(
                application_id=application_id,
                channel=payload.channel,
                body=_safe_format(
                    "Lembrete: entrevista para {job_title} em {interview_at}, local {interview_location}.",
                    vars_reminder,
                ),
                send_at=reminder_at,
                idempotency_key=f"{x_idempotency_key or ''}-r{hours_before}",
            )
            exists = db.execute(select(CommunicationEvent).where(CommunicationEvent.message_id == reminder_message_id)).scalars().first()
            if exists:
                created.append(exists)
                continue
            reminder = CommunicationEvent(
                application_id=application_id,
                channel=payload.channel,
                message_id=reminder_message_id,
                event_type="interview_reminder",
                status="planned",
                template_name=payload.template_name,
                subject=_safe_format("Lembrete de entrevista ({hours_before}h) - {job_title}", vars_reminder),
                body=_safe_format(
                    "Lembrete: entrevista para {job_title} em {interview_at}, local {interview_location}.",
                    vars_reminder,
                ),
                payload_json=json.dumps({"variables": vars_reminder, "kind": "reminder"}, ensure_ascii=False),
                scheduled_for=reminder_at,
                sent_at=None,
                attempts=0,
                max_attempts=max(1, int(get_settings().communication_dispatch_max_retries or 3)),
                next_attempt_at=reminder_at,
                error_message=None,
                created_by=payload.created_by,
            )
            created.append(reminder)
            db.add(reminder)

    db.commit()
    for row in created:
        db.refresh(row)

    AuditService(db).log(
        action="communications.schedule_interview",
        resource_type="application",
        resource_id=str(application_id),
        ip=request.client.host if request.client else None,
        metadata={"channel": payload.channel, "auto_reminders": payload.auto_reminders, "events": len(created)},
    )
    return created


@router.post("/dispatch/run")
def run_dispatch(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    result = CommunicationDispatcherService(db).dispatch_due(limit=limit)
    AuditService(db).log(
        action="communications.dispatch.run",
        resource_type="communications",
        resource_id="dispatch",
        ip=request.client.host if request.client else None,
        metadata={"limit": limit, "processed": result.get("processed"), "sent": result.get("sent"), "failed": result.get("failed")},
    )
    return result


@router.get("/dispatch/stats")
def dispatch_stats(
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    return CommunicationDispatcherService(db).stats()


def _load_application_context(*, db: Session, application_id: int) -> tuple[Application, Candidate, Job]:
    row = db.execute(
        select(Application, Candidate, Job)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Job, Job.id == Application.job_id)
        .where(Application.id == application_id)
        .limit(1)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")
    app, cand, job = row
    return app, cand, job


def _find_template(*, db: Session, channel: str, template_name: str | None) -> MessageTemplate | None:
    if not template_name:
        return None
    repo = TemplateRepository(db)
    for item in repo.list():
        if item.channel == channel and item.name == template_name:
            if (item.status or "").lower() != "approved":
                continue
            return item
    return None


def _default_variables(*, app: Application, cand: Candidate, job: Job) -> dict:
    return {
        "candidate_name": cand.full_name or "",
        "candidate_email": cand.email or "",
        "candidate_phone": cand.phone or "",
        "job_title": job.title or "",
        "application_stage": app.stage or "",
    }


def _safe_format(template: str | None, variables: dict) -> str:
    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return str(template or "").format_map(_SafeDict(**(variables or {})))


def _build_message_id(*, application_id: int, channel: str, body: str, send_at: datetime, idempotency_key: str | None) -> str:
    if idempotency_key:
        key = idempotency_key.strip()
        if key:
            return f"idemp-{key[:64]}"
    base = f"{application_id}|{channel}|{send_at.isoformat()}|{body}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:28]
    return f"msg-{digest}"
