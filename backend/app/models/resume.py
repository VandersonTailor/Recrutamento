from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import SourceChannel


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("file_hash", name="uq_resume_file_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)

    source_channel: Mapped[str] = mapped_column(String(20), default=SourceChannel.unknown.value, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    department: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)

    original_filename: Mapped[str | None] = mapped_column(String(260), nullable=True)
    file_path: Mapped[str] = mapped_column(String(600))
    file_hash: Mapped[str] = mapped_column(String(80))
    filename_cargo: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    filename_cnh: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    filename_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    processing_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(nullable=True)
    requires_manual_review: Mapped[bool] = mapped_column(default=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    missing_in_storage: Mapped[bool] = mapped_column(default=False, index=True)
    missing_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="resumes")  # type: ignore[name-defined]
