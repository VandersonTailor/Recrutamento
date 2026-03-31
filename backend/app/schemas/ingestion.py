from datetime import datetime

from pydantic import BaseModel, Field


class IngestionScanRequest(BaseModel):
    job_id: int | None = None
    force_reanalyze: bool = False


class IngestionScanResult(BaseModel):
    scanned_files: int
    created_candidates: int
    created_resumes: int
    created_applications: int
    updated_applications: int


class IngestionReport(BaseModel):
    file_path: str
    cargo: str | None = None
    setor: str | None = None
    nome: str | None = None
    origem: str = Field(default="EMAIL")
    received_at: datetime | None = None
    sender_email: str | None = None
    subject: str | None = None


class IngestionJobCreate(BaseModel):
    job_id: int | None = None
    force_reanalyze: bool = False


class IngestionJobOut(BaseModel):
    id: int
    status: str
    job_id: int | None = None
    force_reanalyze: bool
    attempts: int
    max_attempts: int
    requested_by: str
    requested_ip: str | None = None
    requested_at: datetime
    next_attempt_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_json: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class IngestionQueueStatsOut(BaseModel):
    pending: int
    running: int
    completed: int
    failed: int
    retrying: int
    oldest_pending_at: datetime | None = None
