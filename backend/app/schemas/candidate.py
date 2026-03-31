from datetime import datetime

from pydantic import BaseModel, Field


class CandidateCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None
    linkedin: str | None = Field(default=None, max_length=260)


class CandidateOut(BaseModel):
    id: int
    full_name: str
    email: str | None
    phone: str | None
    address: str | None
    linkedin: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
