from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion_job import IngestionJob
from app.services.broker_queue import BrokerQueue
from app.services.ingestion import IngestionService


class IngestionQueueService:
    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        *,
        requested_by: str,
        requested_ip: str | None,
        job_id: int | None,
        force_reanalyze: bool,
    ) -> IngestionJob:
        settings = get_settings()
        row = IngestionJob(
            status="pending",
            requested_by=requested_by,
            requested_ip=requested_ip,
            job_id=job_id,
            force_reanalyze=force_reanalyze,
            attempts=0,
            max_attempts=max(1, int(settings.ingestion_queue_max_retries)),
            next_attempt_at=datetime.utcnow(),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        settings = get_settings()
        if settings.broker_enabled:
            BrokerQueue().publish("ocr_queue", {"ingestion_job_id": row.id, "job_id": row.job_id, "force_reanalyze": row.force_reanalyze})
        return row

    def list_jobs(self, *, status: str | None = None, limit: int = 100) -> list[IngestionJob]:
        stmt = select(IngestionJob).order_by(IngestionJob.requested_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(IngestionJob.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def stats(self) -> dict:
        statuses = ["pending", "running", "completed", "failed", "retrying"]
        counts = {s: 0 for s in statuses}
        rows = (
            self.db.execute(select(IngestionJob.status, func.count(IngestionJob.id)).group_by(IngestionJob.status))
            .all()
        )
        for status, count in rows:
            if status in counts:
                counts[status] = int(count)
        oldest_pending = (
            self.db.execute(
                select(IngestionJob.requested_at)
                .where(IngestionJob.status.in_(["pending", "retrying"]))
                .order_by(IngestionJob.requested_at.asc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        counts["oldest_pending_at"] = oldest_pending
        return counts

    def get_job(self, *, ingestion_job_id: int) -> IngestionJob | None:
        return self.db.get(IngestionJob, ingestion_job_id)

    def process_next(self) -> IngestionJob | None:
        now = datetime.utcnow()
        row = (
            self.db.execute(
                select(IngestionJob)
                .where(
                    IngestionJob.status.in_(["pending", "retrying"]),
                    (IngestionJob.next_attempt_at.is_(None) | (IngestionJob.next_attempt_at <= now)),
                )
                .order_by(IngestionJob.requested_at.asc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if not row:
            return None

        row.status = "running"
        row.started_at = datetime.utcnow()
        row.error_message = None
        self.db.add(row)
        self.db.commit()

        try:
            result = IngestionService(self.db).scan_recv_dir(job_id=row.job_id, force_reanalyze=row.force_reanalyze)
            row.status = "completed"
            row.result_json = json.dumps(result, ensure_ascii=False)
            row.finished_at = datetime.utcnow()
            row.next_attempt_at = None
            self.db.add(row)
            self.db.commit()
        except Exception as exc:
            row.error_message = str(exc)
            row.finished_at = datetime.utcnow()
            row.attempts = int(row.attempts or 0) + 1
            if row.attempts >= int(row.max_attempts or 1):
                row.status = "failed"
                row.next_attempt_at = None
            else:
                row.status = "retrying"
                row.next_attempt_at = datetime.utcnow().replace(microsecond=0) + _backoff_delay(row.attempts)
            self.db.add(row)
            self.db.commit()

        self.db.refresh(row)
        return row


def _backoff_delay(attempt: int):
    base = max(1, int(get_settings().ingestion_queue_backoff_seconds))
    seconds = min(900, base * (2 ** max(0, attempt - 1)))
    from datetime import timedelta

    return timedelta(seconds=seconds)
