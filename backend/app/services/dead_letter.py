from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.communication_event import CommunicationEvent
from app.models.dead_letter_event import DeadLetterEvent


class DeadLetterService:
    def __init__(self, db: Session):
        self.db = db

    def push(self, *, source_queue: str, source_id: str, reason: str, payload: dict | None = None) -> DeadLetterEvent:
        row = DeadLetterEvent(
            source_queue=source_queue,
            source_id=source_id,
            reason=reason,
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
            status="open",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list(self, *, status: str | None = None, limit: int = 100) -> list[DeadLetterEvent]:
        stmt = select(DeadLetterEvent).order_by(DeadLetterEvent.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(DeadLetterEvent.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def reprocess_communication(self, *, dlq_id: int) -> dict:
        row = self.db.get(DeadLetterEvent, dlq_id)
        if not row:
            return {"status": "not_found"}
        if row.source_queue != "communications":
            return {"status": "unsupported_source"}
        event = self.db.get(CommunicationEvent, int(row.source_id))
        if not event:
            row.status = "resolved"
            row.reprocessed_at = datetime.utcnow()
            self.db.add(row)
            self.db.commit()
            return {"status": "source_missing"}

        event.status = "retrying"
        event.next_attempt_at = datetime.utcnow()
        event.error_message = None
        self.db.add(event)
        row.status = "reprocessed"
        row.reprocessed_at = datetime.utcnow()
        self.db.add(row)
        self.db.commit()
        return {"status": "requeued", "communication_event_id": event.id}
