from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_queue: Mapped[str] = mapped_column(String(80), index=True)
    source_id: Mapped[str] = mapped_column(String(80), index=True)
    reason: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    reprocessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
