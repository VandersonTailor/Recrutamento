from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.models.candidate import Candidate
from app.models.candidate_consent import CandidateConsent
from app.services.audit import AuditService


router = APIRouter()


class ConsentUpsert(BaseModel):
    channel: str = Field(max_length=20)
    status: str = Field(max_length=20)  # granted/revoked/pending
    source: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=300)
    updated_by: str | None = Field(default=None, max_length=120)


@router.get("/candidate/{candidate_id}")
def get_candidate_consents(
    candidate_id: int,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    rows = (
        db.execute(
            select(CandidateConsent)
            .where(CandidateConsent.candidate_id == candidate_id)
            .order_by(CandidateConsent.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return rows


@router.put("/candidate/{candidate_id}")
def upsert_candidate_consent(
    candidate_id: int,
    payload: ConsentUpsert,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidato não encontrado")
    row = (
        db.execute(
            select(CandidateConsent).where(
                CandidateConsent.candidate_id == candidate_id,
                CandidateConsent.channel == payload.channel,
            )
        )
        .scalars()
        .first()
    )
    if not row:
        row = CandidateConsent(candidate_id=candidate_id, channel=payload.channel)
    row.status = payload.status
    row.source = payload.source
    row.note = payload.note
    row.updated_by = payload.updated_by
    db.add(row)
    db.commit()
    db.refresh(row)
    AuditService(db).log(
        action="consents.upsert",
        resource_type="candidate",
        resource_id=str(candidate_id),
        ip=request.client.host if request.client else None,
        metadata={"channel": payload.channel, "status": payload.status},
    )
    return row
