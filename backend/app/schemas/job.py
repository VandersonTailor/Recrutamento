from datetime import datetime

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    description: str | None = None
    requirements: str | None = None
    ranking_profile: dict | None = None
    is_active: bool = True


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    description: str | None = None
    requirements: str | None = None
    ranking_profile: dict | None = None
    is_active: bool | None = None


class JobOut(BaseModel):
    id: int
    title: str
    department: str | None
    description: str | None
    requirements: str | None
    ranking_profile: dict | str | None = None
    is_active: bool
    created_at: datetime
    closed_at: datetime | None = None
    close_reason: str | None = None

    model_config = {"from_attributes": True}
