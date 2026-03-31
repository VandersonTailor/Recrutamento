from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CommunicationEvent(Base):
    __tablename__ = "communication_events"
    __table_args__ = (UniqueConstraint("message_id", name="uq_communication_message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)

    channel: Mapped[str] = mapped_column(String(20), index=True)
    message_id: Mapped[str] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)
    template_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
