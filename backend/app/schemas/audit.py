from datetime import datetime

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    actor: str
    action: str
    resource_type: str | None
    resource_id: str | None
    ip: str | None
    metadata_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
