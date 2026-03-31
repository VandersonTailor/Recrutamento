from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StageAutomationRule(Base):
    __tablename__ = "stage_automation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    from_stage: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    to_stage: Mapped[str] = mapped_column(String(40), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp")
    template_name: Mapped[str] = mapped_column(String(120))
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    variables_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
