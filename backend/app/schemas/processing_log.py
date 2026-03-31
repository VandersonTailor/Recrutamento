from datetime import datetime

from pydantic import BaseModel


class ProcessingLogOut(BaseModel):
    id: int
    file_path: str
    department: str | None = None
    status: str
    message: str | None = None
    duration_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
