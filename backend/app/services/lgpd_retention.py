from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.candidate_pii_vault import CandidatePIIVault
from app.models.resume import Resume
from app.services.pii_crypto import encrypt_text


def encrypt_candidate_pii(db: Session, candidate: Candidate) -> CandidatePIIVault:
    row = (
        db.execute(select(CandidatePIIVault).where(CandidatePIIVault.candidate_id == candidate.id))
        .scalars()
        .first()
    )
    if not row:
        row = CandidatePIIVault(candidate_id=candidate.id)
    row.email_enc = encrypt_text(candidate.email)
    row.phone_enc = encrypt_text(candidate.phone)
    row.address_enc = encrypt_text(candidate.address)
    row.linkedin_enc = encrypt_text(candidate.linkedin)
    db.add(row)
    db.flush()
    return row


def run_retention_cycle(db: Session, *, older_than_days: int | None = None, limit: int = 300) -> dict:
    if older_than_days is None:
        older_than_days = int(get_settings().lgpd_default_retention_days)
    cutoff = datetime.utcnow() - timedelta(days=max(1, older_than_days))

    candidates = (
        db.execute(
            select(Candidate)
            .where(Candidate.created_at < cutoff)
            .order_by(Candidate.created_at.asc())
            .limit(max(1, min(limit, 2000)))
        )
        .scalars()
        .all()
    )
    updated = 0
    skipped = 0
    for cand in candidates:
        has_active = (
            db.execute(
                select(Application.id)
                .where(
                    Application.candidate_id == cand.id,
                    Application.stage.notin_(["Aprovado", "Reprovado", "Banco de talentos"]),
                )
                .limit(1)
            ).first()
            is not None
        )
        if has_active:
            skipped += 1
            continue
        encrypt_candidate_pii(db, cand)
        cand.full_name = f"ANON-{cand.id}"
        cand.email = None
        cand.phone = None
        cand.address = None
        cand.linkedin = None
        db.add(cand)
        resumes = db.execute(select(Resume).where(Resume.candidate_id == cand.id)).scalars().all()
        for resume in resumes:
            resume.extracted_text = None
            resume.parsed_json = None
            resume.structured_json = None
            resume.review_reason = "dados_anonimizados_lgpd_auto"
            db.add(resume)
        updated += 1
    db.commit()
    return {"updated": updated, "skipped": skipped, "cutoff": cutoff.isoformat()}
