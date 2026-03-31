from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MatchingCalibration(Base):
    __tablename__ = "matching_calibrations"
    __table_args__ = (UniqueConstraint("job_id", "department", name="uq_matching_calibration_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    score_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    score_bias: Mapped[float] = mapped_column(Float, default=0.0)
    min_score_floor: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
