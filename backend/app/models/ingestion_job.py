from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    force_reanalyze: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    requested_by: Mapped[str] = mapped_column(String(120), default="system")
    requested_ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
