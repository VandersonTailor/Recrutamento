from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.candidate_consent import CandidateConsent
from app.models.communication_event import CommunicationEvent
from app.models.dead_letter_event import DeadLetterEvent
from app.models.processing_log import ProcessingLog
from app.services.dead_letter import DeadLetterService
from app.services.metrics import COMM_BACKLOG, COMM_DISPATCH_LATENCY, COMM_DISPATCH_TOTAL, DLQ_BACKLOG
from app.services.communication_sender import CommunicationSender, NonRetryableSendError


class CommunicationDispatcherService:
    def __init__(self, db: Session, sender: CommunicationSender | None = None):
        self.db = db
        self.sender = sender or CommunicationSender()

    def dispatch_due(self, *, limit: int | None = None) -> dict:
        settings = get_settings()
        batch_limit = int(limit or settings.communication_dispatch_batch_size or 50)
        batch_limit = max(1, min(500, batch_limit))

        now = datetime.utcnow()
        due_events = (
            self.db.execute(
                select(CommunicationEvent)
                .where(
                    CommunicationEvent.status.in_(["planned", "retrying"]),
                    (
                        (CommunicationEvent.next_attempt_at.is_not(None) & (CommunicationEvent.next_attempt_at <= now))
                        | (
                            CommunicationEvent.next_attempt_at.is_(None)
                            & CommunicationEvent.scheduled_for.is_not(None)
                            & (CommunicationEvent.scheduled_for <= now)
                        )
                    ),
                )
                .order_by(CommunicationEvent.next_attempt_at.asc(), CommunicationEvent.scheduled_for.asc())
                .limit(batch_limit)
            )
            .scalars()
            .all()
        )
        if not due_events:
            return {"processed": 0, "sent": 0, "failed": 0, "items": []}

        sent = 0
        failed = 0
        retrying = 0
        items: list[dict] = []
        for event in due_events:
            try:
                recipient_email, recipient_phone = self._resolve_recipients(event)
                self._ensure_consent(event=event)
                t0 = datetime.utcnow()
                send_meta = self.sender.send(event=event, recipient_email=recipient_email, recipient_phone=recipient_phone)
                latency = max(0.0, (datetime.utcnow() - t0).total_seconds())
                COMM_DISPATCH_LATENCY.labels(channel=event.channel).observe(latency)
                event.status = "sent"
                event.sent_at = datetime.utcnow()
                event.next_attempt_at = None
                event.error_message = None
                sent += 1
                COMM_DISPATCH_TOTAL.labels(status="sent", channel=event.channel).inc()
                items.append(
                    {
                        "id": event.id,
                        "status": "sent",
                        "channel": event.channel,
                        "event_type": event.event_type,
                        "meta": send_meta,
                    }
                )
                self._log_dispatch(event=event, status="success", message=f"Dispatched via {send_meta.get('provider')} ({send_meta.get('mode')})")
            except NonRetryableSendError as exc:
                event.attempts = int(event.attempts or 0) + 1
                event.status = "failed"
                event.error_message = str(exc)
                event.next_attempt_at = None
                failed += 1
                COMM_DISPATCH_TOTAL.labels(status="failed", channel=event.channel).inc()
                DeadLetterService(self.db).push(
                    source_queue="communications",
                    source_id=str(event.id),
                    reason=f"non_retryable: {exc}",
                    payload={"message_id": event.message_id, "channel": event.channel},
                )
                items.append({"id": event.id, "status": "failed", "channel": event.channel, "event_type": event.event_type, "error": str(exc)})
                self._log_dispatch(event=event, status="error", message=f"Non-retryable: {exc}")
            except Exception as exc:
                event.attempts = int(event.attempts or 0) + 1
                max_attempts = int(event.max_attempts or settings.communication_dispatch_max_retries or 3)
                if event.attempts >= max_attempts:
                    event.status = "failed"
                    event.next_attempt_at = None
                    failed += 1
                    COMM_DISPATCH_TOTAL.labels(status="failed", channel=event.channel).inc()
                    DeadLetterService(self.db).push(
                        source_queue="communications",
                        source_id=str(event.id),
                        reason=f"exhausted_retries: {exc}",
                        payload={"message_id": event.message_id, "channel": event.channel},
                    )
                    out_status = "failed"
                else:
                    event.status = "retrying"
                    event.next_attempt_at = datetime.utcnow().replace(microsecond=0) + _dispatch_backoff_delay(event.attempts)
                    retrying += 1
                    COMM_DISPATCH_TOTAL.labels(status="retrying", channel=event.channel).inc()
                    out_status = "retrying"
                event.error_message = str(exc)
                items.append({"id": event.id, "status": out_status, "channel": event.channel, "event_type": event.event_type, "error": str(exc)})
                self._log_dispatch(event=event, status="error", message=f"Dispatch error: {exc}")
            self.db.add(event)

        self.db.commit()
        self._refresh_gauges()
        return {"processed": len(due_events), "sent": sent, "failed": failed, "retrying": retrying, "items": items}

    def stats(self) -> dict:
        rows = self.db.execute(
            select(CommunicationEvent.status, func.count(CommunicationEvent.id)).group_by(CommunicationEvent.status)
        ).all()
        counts = {"planned": 0, "retrying": 0, "sent": 0, "failed": 0}
        for status, qty in rows:
            if status in counts:
                counts[status] = int(qty)

        oldest_due = (
            self.db.execute(
                select(CommunicationEvent.next_attempt_at, CommunicationEvent.scheduled_for)
                .where(CommunicationEvent.status.in_(["planned", "retrying"]))
                .order_by(CommunicationEvent.next_attempt_at.asc(), CommunicationEvent.scheduled_for.asc())
                .limit(1)
            )
            .first()
        )
        counts["oldest_due_at"] = oldest_due[0] if oldest_due and oldest_due[0] else (oldest_due[1] if oldest_due else None)
        self._refresh_gauges()
        return counts

    def _log_dispatch(self, *, event: CommunicationEvent, status: str, message: str) -> None:
        log = ProcessingLog(
            file_path=f"communication://event/{event.id}",
            department="communications",
            status=status,
            message=message,
            duration_ms=0,
        )
        self.db.add(log)

    def _resolve_recipients(self, event: CommunicationEvent) -> tuple[str | None, str | None]:
        email = None
        phone = None
        try:
            payload = json.loads(event.payload_json or "{}")
            vars_data = payload.get("variables") or payload
            if isinstance(vars_data, dict):
                email = vars_data.get("candidate_email")
                phone = vars_data.get("candidate_phone")
        except Exception:
            email = None
            phone = None

        if email and phone:
            return str(email), str(phone)

        row = self.db.execute(
            select(Candidate.email, Candidate.phone)
            .select_from(Application)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .where(Application.id == event.application_id)
            .limit(1)
        ).first()
        if row:
            email = email or row[0]
            phone = phone or row[1]
        return (str(email) if email else None, str(phone) if phone else None)

    def _ensure_consent(self, *, event: CommunicationEvent) -> None:
        if str(event.channel).lower() != "whatsapp":
            return
        row = (
            self.db.execute(
                select(CandidateConsent.status)
                .select_from(Application)
                .join(CandidateConsent, CandidateConsent.candidate_id == Application.candidate_id, isouter=True)
                .where(
                    Application.id == event.application_id,
                    CandidateConsent.channel == "whatsapp",
                )
                .limit(1)
            )
            .first()
        )
        if not row:
            # padrão conservador: consentimento implícito legado
            return
        status = str(row[0] or "").lower()
        if status not in {"granted", "optin", "aceito"}:
            raise NonRetryableSendError("Consentimento WhatsApp não concedido para este candidato.")

    def _refresh_gauges(self) -> None:
        backlog = int(
            self.db.execute(
                select(func.count(CommunicationEvent.id)).where(CommunicationEvent.status.in_(["planned", "retrying"]))
            ).scalar_one()
            or 0
        )
        dlq = int(
            self.db.execute(
                select(func.count(DeadLetterEvent.id)).where(DeadLetterEvent.status == "open")
            ).scalar_one()
            or 0
        )
        COMM_BACKLOG.set(backlog)
        DLQ_BACKLOG.set(dlq)


def _dispatch_backoff_delay(attempt: int) -> timedelta:
    settings = get_settings()
    base = max(1, int(settings.communication_dispatch_backoff_seconds or 30))
    seconds = min(1800, base * (2 ** max(0, attempt - 1)))
    return timedelta(seconds=seconds)
