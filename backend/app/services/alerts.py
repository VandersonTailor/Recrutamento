from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.communication_event import CommunicationEvent
from app.models.ingestion_job import IngestionJob


def collect_active_alerts(db: Session) -> list[dict]:
    now = datetime.utcnow()
    alerts: list[dict] = []

    overdue_sla = (
        db.execute(
            select(CommunicationEvent)
            .where(
                CommunicationEvent.status.in_(["planned", "retrying"]),
                CommunicationEvent.scheduled_for.is_not(None),
                CommunicationEvent.scheduled_for < (now - timedelta(minutes=15)),
            )
            .limit(50)
        )
        .scalars()
        .all()
    )
    if overdue_sla:
        alerts.append(
            {
                "code": "COMM_SLA_OVERDUE",
                "severity": "high",
                "count": len(overdue_sla),
                "message": "Mensagens pendentes além do SLA operacional (15 min).",
            }
        )

    provider_failures = (
        db.execute(
            select(CommunicationEvent)
            .where(
                CommunicationEvent.status == "failed",
                CommunicationEvent.sent_at.is_(None),
                CommunicationEvent.created_at >= (now - timedelta(hours=1)),
            )
            .limit(100)
        )
        .scalars()
        .all()
    )
    if provider_failures:
        alerts.append(
            {
                "code": "COMM_PROVIDER_FAILURE",
                "severity": "critical",
                "count": len(provider_failures),
                "message": "Falhas recentes de provedor de comunicação.",
            }
        )

    stalled_queue = (
        db.execute(
            select(IngestionJob)
            .where(
                IngestionJob.status.in_(["pending", "retrying"]),
                IngestionJob.requested_at <= (now - timedelta(minutes=30)),
            )
            .limit(20)
        )
        .scalars()
        .all()
    )
    if stalled_queue:
        alerts.append(
            {
                "code": "OCR_QUEUE_STALLED",
                "severity": "medium",
                "count": len(stalled_queue),
                "message": "Fila OCR/NLP com itens antigos sem processamento.",
            }
        )
    return alerts
