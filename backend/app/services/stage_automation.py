from __future__ import annotations

import json
from datetime import datetime, timedelta
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.communication_event import CommunicationEvent
from app.models.job import Job
from app.models.stage_automation_rule import StageAutomationRule
from app.models.message_template import MessageTemplate


def run_stage_automations(*, db: Session, application_id: int, from_stage: str | None, to_stage: str) -> list[CommunicationEvent]:
    app = db.get(Application, application_id)
    if not app:
        return []
    candidate = db.get(Candidate, app.candidate_id)
    job = db.get(Job, app.job_id)
    if not candidate or not job:
        return []

    rules = (
        db.execute(
            select(StageAutomationRule).where(
                StageAutomationRule.enabled == 1,
                StageAutomationRule.to_stage == to_stage,
                (StageAutomationRule.from_stage.is_(None) | (StageAutomationRule.from_stage == from_stage)),
                (StageAutomationRule.job_id.is_(None) | (StageAutomationRule.job_id == app.job_id)),
            )
        )
        .scalars()
        .all()
    )
    if not rules:
        return []

    now = datetime.utcnow()
    out: list[CommunicationEvent] = []
    settings = get_settings()
    for rule in rules:
        template = (
            db.execute(
                select(MessageTemplate).where(
                    MessageTemplate.channel == rule.channel,
                    MessageTemplate.name == rule.template_name,
                    MessageTemplate.status == "approved",
                )
                .order_by(MessageTemplate.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if not template:
            continue
        vars_data = {
            "candidate_name": candidate.full_name or "",
            "candidate_email": candidate.email or "",
            "candidate_phone": candidate.phone or "",
            "job_title": job.title or "",
            "application_stage": to_stage,
        }
        if rule.variables_json:
            try:
                vars_data.update(json.loads(rule.variables_json))
            except Exception:
                pass

        scheduled = now + timedelta(minutes=max(0, int(rule.delay_minutes or 0)))
        base = f"{app.id}|{rule.channel}|{rule.template_name}|{scheduled.isoformat()}"
        message_id = f"auto-{hashlib.sha1(base.encode('utf-8')).hexdigest()[:24]}"

        existing = (
            db.execute(select(CommunicationEvent).where(CommunicationEvent.message_id == message_id))
            .scalars()
            .first()
        )
        if existing:
            out.append(existing)
            continue

        event = CommunicationEvent(
            application_id=app.id,
            channel=rule.channel,
            message_id=message_id,
            event_type="message",
            status="planned",
            template_name=template.name,
            subject=_safe_format(template.subject, vars_data) if template.subject else None,
            body=_safe_format(template.body, vars_data),
            payload_json=json.dumps({"variables": vars_data, "automation_rule_id": rule.id}, ensure_ascii=False),
            attempts=0,
            max_attempts=max(1, int(settings.communication_dispatch_max_retries or 3)),
            next_attempt_at=scheduled,
            scheduled_for=scheduled,
            created_by=rule.created_by or "automation",
        )
        db.add(event)
        out.append(event)
    db.commit()
    for ev in out:
        db.refresh(ev)
    return out


def _safe_format(template: str | None, variables: dict) -> str:
    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return str(template or "").format_map(_SafeDict(**(variables or {})))
