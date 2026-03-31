from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ResumeFile(Base):
    __tablename__ = "resume_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, index=True)
    md5: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    mime_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
