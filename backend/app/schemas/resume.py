from datetime import datetime

from pydantic import BaseModel


class ResumeOut(BaseModel):
    id: int
    candidate_id: int
    source_channel: str
    received_at: datetime
    department: str | None
    original_filename: str | None
    file_path: str
    file_hash: str
    filename_cargo: str | None = None
    filename_cnh: str | None = None
    filename_date: str | None = None
    imported_at: datetime | None = None
    last_synced_at: datetime | None = None
    processing_status: str | None = None
    created_at: datetime
    extraction_confidence: float | None = None
    requires_manual_review: bool = False
    review_reason: str | None = None

    candidate_name: str | None = None
    current_stage: str | None = None

    model_config = {"from_attributes": True}


class ResumeDetail(ResumeOut):
    extracted_text: str | None
    parsed_json: str | None
    structured_json: str | None = None
    candidate_email: str | None = None
    candidate_phone: str | None = None
    candidate_address: str | None = None
    candidate_linkedin: str | None = None
    professional_summary: str | None = None
    warnings: list[str] = []


class ResumeStructuredUpdate(BaseModel):
    structured_json: dict
    approve_review: bool = True
    review_reason: str | None = None
    extraction_confidence: float | None = None


class ResumeFileUpdate(BaseModel):
    new_department: str | None = None
    new_cargo: str | None = None
    new_candidate_name: str | None = None
    new_filename: str | None = None
    reason: str | None = None
    apply_filename_pattern: bool = True


class ResumeHistoryOut(BaseModel):
    id: int
    resume_id: int
    action: str
    old_value_json: str | None = None
    new_value_json: str | None = None
    reason: str | None = None
    actor: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ResumeDivergenceOut(BaseModel):
    resume_id: int
    candidate_id: int
    candidate_name: str | None = None
    file_name: str | None = None
    department: str | None = None
    filename_cargo: str | None = None
    suggested_cargo: str | None = None
    suggestion_confidence: float | None = None
    reason: str
    requires_review: bool
