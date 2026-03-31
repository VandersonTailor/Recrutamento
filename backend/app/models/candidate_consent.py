from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CandidateConsent(Base):
    __tablename__ = "candidate_consents"
    __table_args__ = (UniqueConstraint("candidate_id", "channel", name="uq_candidate_consent_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="granted", index=True)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
