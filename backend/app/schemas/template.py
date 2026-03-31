from datetime import datetime

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    channel: str = Field(default="email", max_length=20)
    name: str = Field(min_length=2, max_length=120)
    parent_id: int | None = None
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=2)
    created_by: str | None = Field(default=None, max_length=120)


class TemplateOut(BaseModel):
    id: int
    channel: str
    name: str
    version: int
    status: str
    parent_id: int | None
    approved_by: str | None
    approved_at: datetime | None
    subject: str | None
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RenderTemplateRequest(BaseModel):
    subject: str | None = None
    body: str
    variables: dict = Field(default_factory=dict)


class RenderTemplateResponse(BaseModel):
    subject: str | None
    body: str


class TemplateApproveRequest(BaseModel):
    approved_by: str | None = Field(default=None, max_length=120)
