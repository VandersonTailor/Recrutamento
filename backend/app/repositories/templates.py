from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message_template import MessageTemplate


class TemplateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, tpl: MessageTemplate) -> MessageTemplate:
        self.db.add(tpl)
        self.db.commit()
        self.db.refresh(tpl)
        return tpl

    def list(self) -> list[MessageTemplate]:
        stmt = select(MessageTemplate).order_by(MessageTemplate.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def latest_version(self, *, channel: str, name: str) -> int:
        stmt = (
            select(MessageTemplate.version)
            .where(MessageTemplate.channel == channel, MessageTemplate.name == name)
            .order_by(MessageTemplate.version.desc())
            .limit(1)
        )
        return int(self.db.execute(stmt).scalars().first() or 0)
