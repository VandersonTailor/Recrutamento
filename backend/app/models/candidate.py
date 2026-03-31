from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("email", name="uq_candidate_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(260), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    resumes: Mapped[list["Resume"]] = relationship(back_populates="candidate")  # type: ignore[name-defined]
    applications: Mapped[list["Application"]] = relationship(back_populates="candidate")  # type: ignore[name-defined]
