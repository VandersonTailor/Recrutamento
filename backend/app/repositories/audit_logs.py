import json

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(
        self,
        *,
        actor: str = "anonymous",
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        ip: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        row = AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=ip,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
