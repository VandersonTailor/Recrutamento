from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import SourceChannel


class MessageTemplate(Base):
    __tablename__ = "message_templates"
    __table_args__ = (
        UniqueConstraint("name", "channel", "version", name="uq_template_name_channel_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(20), default=SourceChannel.email.value, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft/approved/archived
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("message_templates.id"), nullable=True, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
