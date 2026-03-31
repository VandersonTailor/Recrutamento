from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ResumeChangeHistory(Base):
    __tablename__ = "resume_change_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    old_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
