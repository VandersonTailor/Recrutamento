from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CommunicationEventOut(BaseModel):
    id: int
    application_id: int
    channel: str
    message_id: str
    event_type: str
    status: str
    template_name: str | None = None
    subject: str | None = None
    body: str
    payload_json: str | None = None
    attempts: int = 0
    max_attempts: int = 0
    next_attempt_at: datetime | None = None
    error_message: str | None = None
    scheduled_for: datetime | None = None
    sent_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SendTemplateRequest(BaseModel):
    channel: Literal["whatsapp"] = "whatsapp"
    template_name: str | None = Field(default=None, max_length=120)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = None
    variables: dict = Field(default_factory=dict)
    send_at: datetime | None = None
    created_by: str | None = Field(default=None, max_length=120)


class ScheduleInterviewRequest(BaseModel):
    channel: Literal["whatsapp"] = "whatsapp"
    template_name: str | None = Field(default="convite_entrevista", max_length=120)
    interview_at: datetime
    location: str = Field(default="Sede Carris", max_length=160)
    interviewer: str | None = Field(default=None, max_length=120)
    mode: str = Field(default="Presencial", max_length=40)
    notes: str | None = Field(default=None, max_length=300)
    auto_reminders: bool = True
    created_by: str | None = Field(default=None, max_length=120)


class PendingCommunicationOut(BaseModel):
    total: int
    items: list[CommunicationEventOut]
