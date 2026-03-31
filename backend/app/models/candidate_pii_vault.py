from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CandidatePIIVault(Base):
    __tablename__ = "candidate_pii_vault"
    __table_args__ = (UniqueConstraint("candidate_id", name="uq_candidate_pii_vault"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    email_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
