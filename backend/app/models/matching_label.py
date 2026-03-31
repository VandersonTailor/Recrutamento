from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MatchingLabel(Base):
    __tablename__ = "matching_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(20), index=True)  # approved/rejected/promising
    expected_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
