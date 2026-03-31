from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import ApplicationStage, SeniorityLevel


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_application_candidate_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)

    stage: Mapped[str] = mapped_column(String(40), default=ApplicationStage.recebido.value, index=True)

    score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    score_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    seniority: Mapped[str] = mapped_column(String(20), default=SeniorityLevel.indefinido.value, index=True)
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    concerns: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_role: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    secondary_roles_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="applications")  # type: ignore[name-defined]
    job: Mapped["Job"] = relationship()  # type: ignore[name-defined]
    history: Mapped[list["StageHistory"]] = relationship(back_populates="application")  # type: ignore[name-defined]
