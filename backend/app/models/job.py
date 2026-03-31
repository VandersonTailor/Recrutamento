from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    ranking_profile: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
