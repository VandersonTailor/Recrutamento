from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.config import get_settings
from app.core.security import require_roles
from app.models.candidate import Candidate
from app.models.resume import Resume
from app.repositories.candidates import CandidateRepository
from app.schemas.candidate import CandidateOut
from app.services.audit import AuditService
from app.services.lgpd_retention import encrypt_candidate_pii, run_retention_cycle


router = APIRouter()


@router.get("", response_model=list[CandidateOut])
def list_candidates(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    repo = CandidateRepository(db)
    return repo.list(limit=limit, offset=offset)


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    repo = CandidateRepository(db)
    candidate = repo.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidato não encontrado")
    return candidate


@router.post("/{candidate_id}/anonymize")
def anonymize_candidate(
    candidate_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidato não encontrado")

    encrypt_candidate_pii(db, candidate)
    candidate.full_name = f"ANON-{candidate_id}"
    candidate.email = None
    candidate.phone = None
    candidate.address = None
    candidate.linkedin = None
    db.add(candidate)

    resumes = db.execute(select(Resume).where(Resume.candidate_id == candidate_id)).scalars().all()
    for resume in resumes:
        resume.extracted_text = None
        resume.parsed_json = None
        resume.structured_json = None
        resume.review_reason = "dados_anonimizados_lgpd"
        db.add(resume)

    db.commit()
    AuditService(db).log(
        action="candidates.anonymize",
        resource_type="candidate",
        resource_id=str(candidate_id),
        ip=request.client.host if request.client else None,
        metadata={"resumes_affected": len(resumes)},
    )
    return {"status": "ok", "candidate_id": candidate_id, "resumes_affected": len(resumes)}


@router.post("/lgpd/anonymize-batch")
def anonymize_candidates_batch(
    request: Request,
    older_than_days: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("admin")),
):
    if older_than_days is None:
        older_than_days = int(get_settings().lgpd_default_retention_days)
    result = run_retention_cycle(db, older_than_days=older_than_days, limit=max(1, min(limit, 500)))

    AuditService(db).log(
        action="candidates.lgpd.anonymize_batch",
        ip=request.client.host if request.client else None,
        metadata={"updated": result.get("updated"), "skipped": result.get("skipped"), "older_than_days": older_than_days},
    )
    return {"status": "ok", "updated": result.get("updated"), "skipped": result.get("skipped")}
