from sqlalchemy.orm import Session

from app.repositories.audit_logs import AuditLogRepository


class AuditService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AuditLogRepository(db)

    def log(
        self,
        *,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        ip: str | None = None,
        metadata: dict | None = None,
        actor: str = "anonymous",
    ) -> None:
        self.repo.add(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=ip,
            metadata=metadata,
        )
