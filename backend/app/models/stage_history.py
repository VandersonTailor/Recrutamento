from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StageHistory(Base):
    __tablename__ = "stage_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)

    from_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    application: Mapped["Application"] = relationship(back_populates="history")  # type: ignore[name-defined]
