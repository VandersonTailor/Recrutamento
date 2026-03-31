from datetime import datetime

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    candidate_id: int
    job_id: int


class ApplicationStageUpdate(BaseModel):
    to_stage: str = Field(min_length=2, max_length=40)
    note: str | None = None


class ApplicationOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    stage: str
    score: float | None
    score_justification: str | None
    experience_years: float | None
    seniority: str
    strengths: str | None
    concerns: str | None
    primary_role: str | None = None
    secondary_roles: list[str] = []
    role_confidence: float | None = None
    created_at: datetime
    updated_at: datetime
    stage_entered_at: datetime | None = None
    stage_sla_hours: int | None = None
    stage_elapsed_hours: int | None = None
    stage_overdue: bool | None = None
    stage_overdue_hours: int | None = None

    candidate_name: str | None = None
    job_title: str | None = None

    model_config = {"from_attributes": True}


class ApplicationSLAOut(BaseModel):
    total_in_scope: int
    overdue_count: int
    due_soon_count: int
    items: list[ApplicationOut]
