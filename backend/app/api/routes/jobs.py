from datetime import datetime, timezone
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
import re
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse

from app.core.db import get_db
from app.models.job import Job
from app.models.application import Application
from app.repositories.jobs import JobRepository
from app.schemas.job import JobCreate, JobOut, JobUpdate
from app.schemas.ranking import JobRankingResponse, RankingAuditOut, RankingFeedbackIn, RankingFeedbackOut, ScoringProfileOut, ScoringProfileUpdate
from app.services.audit import AuditService
from app.core.config import get_settings
from app.services.ingestion import IngestionService, infer_setor_from_job_title
from app.services.ranking import RankingService
from app.services.scoring import apply_feedback_to_profile, read_scoring_profile, store_scoring_profile
from app.models.audit_log import AuditLog


router = APIRouter()


@router.get("", response_model=list[JobOut])
def list_jobs(active_only: bool = False, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    return repo.list(active_only=active_only)


@router.post("", response_model=JobOut)
def create_job(payload: JobCreate, request: Request, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    data = payload.model_dump()
    ranking_profile = data.get("ranking_profile")
    if isinstance(ranking_profile, dict):
        data["ranking_profile"] = json.dumps(ranking_profile, ensure_ascii=False)
    if not data.get("department"):
        data["department"] = _infer_department_from_folders(title=data.get("title") or "")
    job = Job(**data)
    job = repo.create(job)
    try:
        # Importa currículos da pasta certa para a vaga recém-criada,
        # seguindo a mesma dinâmica do bot (setor + cargo no nome do arquivo).
        ingest_result = IngestionService(db).scan_recv_dir(job_id=job.id, force_reanalyze=False)
        AuditService(db).log(
            action="jobs.ingestion_scan",
            resource_type="job",
            resource_id=str(job.id),
            ip=request.client.host if request.client else None,
            metadata=ingest_result,
        )
    except Exception:
        pass
    try:
        # Auto-match: cria candidaturas iniciais com base nos currículos do departamento
        if job.department:
            rs = RankingService(db)
            ranked = rs.rank_job(job_id=job.id, department=job.department, min_score=50.0, q=None, limit=30, use_cache=False)
            from app.repositories.applications import ApplicationRepository
            from app.models.application import Application
            from app.models.common import ApplicationStage
            from app.models.stage_history import StageHistory
            app_repo = ApplicationRepository(db)
            created = 0
            for it in ranked.get("items", []):
                cand_id = it["candidate_id"]
                existing = app_repo.get_by_candidate_job(candidate_id=cand_id, job_id=job.id)
                if existing:
                    continue
                app = app_repo.create(Application(candidate_id=cand_id, job_id=job.id, stage=ApplicationStage.recebido.value, score=it["match_percent"], score_justification=f"Auto-match {int(it['match_percent'])}%"))
                db.add(StageHistory(application_id=app.id, from_stage=None, to_stage=app.stage, note="Criada por auto-match"))
                db.commit()
                created += 1
            AuditService(db).log(action="jobs.auto_match", resource_type="job", resource_id=str(job.id), ip=request.client.host if request.client else None, metadata={"created": created})
    except Exception:
        pass
    AuditService(db).log(action="jobs.create", resource_type="job", resource_id=str(job.id), ip=request.client.host if request.client else None)
    return job


@router.patch("/{job_id}", response_model=JobOut)
def update_job(job_id: int, payload: JobUpdate, request: Request, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "ranking_profile" and isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False)
        setattr(job, k, v)
    job = repo.update(job)
    AuditService(db).log(action="jobs.update", resource_type="job", resource_id=str(job.id), ip=request.client.host if request.client else None)
    return job


@router.post("/{job_id}/close", response_model=JobOut)
def close_job(job_id: int, reason: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")
    job.is_active = False
    job.closed_at = datetime.utcnow()
    job.close_reason = reason
    job = repo.update(job)
    AuditService(db).log(action="jobs.close", resource_type="job", resource_id=str(job.id), ip=request.client.host if request.client else None, metadata={"reason": reason})
    return job


@router.post("/{job_id}/reopen", response_model=JobOut)
def reopen_job(job_id: int, request: Request = None, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")
    job.is_active = True
    job.closed_at = None
    job = repo.update(job)
    AuditService(db).log(action="jobs.reopen", resource_type="job", resource_id=str(job.id), ip=request.client.host if request.client else None)
    return job


@router.post("/{job_id}/delete", response_model=JobOut)
def delete_job(job_id: int, reason: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")
    job.deleted = True
    job.is_active = False
    job.closed_at = job.closed_at or datetime.utcnow()
    job.close_reason = reason
    job = repo.update(job)
    AuditService(db).log(action="jobs.delete", resource_type="job", resource_id=str(job.id), ip=request.client.host if request.client else None, metadata={"reason": reason})
    return job


@router.get("/{job_id}/ranking", response_model=JobRankingResponse)
def job_ranking(
    job_id: int,
    request: Request,
    department: str | None = None,
    min_score: float | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    result = RankingService(db).rank_job(job_id=job_id, department=department, min_score=min_score, q=q, limit=limit, use_cache=False)
    AuditService(db).log(
        action="jobs.ranking",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
        metadata={"department": department, "min_score": min_score, "q": q, "limit": limit},
    )
    return result


@router.get("/{job_id}/ranking-profile", response_model=ScoringProfileOut)
def get_ranking_profile(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = JobRepository(db).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    profile = read_scoring_profile(job)
    AuditService(db).log(
        action="jobs.ranking_profile.get",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
    )
    return profile


@router.patch("/{job_id}/ranking-profile", response_model=ScoringProfileOut)
def update_ranking_profile(job_id: int, payload: ScoringProfileUpdate, request: Request, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    profile = store_scoring_profile(job, payload.model_dump(exclude_none=True))
    repo.update(job)
    AuditService(db).log(
        action="jobs.ranking_profile.update",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
        metadata=profile,
    )
    return profile


@router.post("/{job_id}/ranking-feedback", response_model=RankingFeedbackOut)
def ranking_feedback(job_id: int, payload: RankingFeedbackIn, request: Request, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    app = db.get(Application, payload.application_id)
    if not app or app.job_id != job_id:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada para esta vaga")

    signal = _build_feedback_signal(app)
    current = read_scoring_profile(job)
    updated = apply_feedback_to_profile(profile=current, signal=signal, decision=payload.decision)
    job.ranking_profile = json.dumps(updated, ensure_ascii=False)
    repo.update(job)

    AuditService(db).log(
        action="jobs.ranking_feedback",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
        metadata={
            "application_id": payload.application_id,
            "decision": payload.decision,
            "signal": signal,
            "note": payload.note,
            "before_profile": current,
            "after_profile": updated,
        },
    )
    return {
        "job_id": job_id,
        "application_id": payload.application_id,
        "decision": payload.decision,
        "updated_profile": updated,
    }


@router.get("/{job_id}/ranking/audit", response_model=RankingAuditOut)
def ranking_audit(
    job_id: int,
    request: Request,
    decision: str | None = None,
    application_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    min_score: float | None = None,
    limit_events: int = Query(default=50, ge=1, le=300),
    snapshot_limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    payload = _build_ranking_audit_payload(
        db=db,
        job=job,
        decision=decision,
        application_id=application_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        min_score=min_score,
        limit_events=limit_events,
        snapshot_limit=snapshot_limit,
    )
    AuditService(db).log(
        action="jobs.ranking_audit",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
        metadata={
            "events": len(payload.get("feedback_events", [])),
            "filters": {
                "decision": decision,
                "application_id": application_id,
                "date_from": date_from,
                "date_to": date_to,
                "q": q,
                "min_score": min_score,
                "limit_events": limit_events,
                "snapshot_limit": snapshot_limit,
            },
        },
    )
    return payload


@router.get("/{job_id}/ranking/audit/export")
def export_ranking_audit(
    job_id: int,
    request: Request,
    decision: str | None = None,
    application_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    min_score: float | None = None,
    limit_events: int = Query(default=200, ge=1, le=500),
    snapshot_limit: int = Query(default=200, ge=1, le=500),
    format: str = Query(default="csv"),
    db: Session = Depends(get_db),
):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    payload = _build_ranking_audit_payload(
        db=db,
        job=job,
        decision=decision,
        application_id=application_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        min_score=min_score,
        limit_events=limit_events,
        snapshot_limit=snapshot_limit,
    )

    AuditService(db).log(
        action="jobs.ranking_audit.export",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
        metadata={"format": format, "events": len(payload.get("feedback_events", [])), "snapshot": len(payload.get("ranking_snapshot", []))},
    )

    if (format or "").lower() == "json":
        return payload
    if (format or "").lower() != "csv":
        raise HTTPException(status_code=400, detail="Formato inválido. Use csv ou json.")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["record_type", "job_id", "event_id", "created_at", "application_id", "decision", "note", "candidate_id", "candidate_name", "rank_position", "match_percent", "rank_reason"])

    for event in payload.get("feedback_events", []):
        writer.writerow(
            [
                "feedback_event",
                payload.get("job_id"),
                event.get("id"),
                event.get("created_at"),
                event.get("application_id"),
                event.get("decision"),
                event.get("note"),
                "",
                "",
                "",
                "",
                "",
            ]
        )
    for item in payload.get("ranking_snapshot", []):
        writer.writerow(
            [
                "ranking_snapshot",
                payload.get("job_id"),
                "",
                "",
                item.get("application_id"),
                "",
                "",
                item.get("candidate_id"),
                item.get("candidate_name"),
                item.get("rank_position"),
                item.get("match_percent"),
                item.get("rank_reason"),
            ]
        )

    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv")


@router.get("/{job_id}/ranking/export")
def export_job_ranking_csv(
    job_id: int,
    request: Request,
    department: str | None = None,
    min_score: float | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    result = RankingService(db).rank_job(job_id=job_id, department=department, min_score=min_score, q=q, limit=limit, use_cache=False)
    AuditService(db).log(
        action="jobs.ranking_export",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
        metadata={"department": department, "min_score": min_score, "q": q, "limit": limit},
    )

    def _gen():
        yield "candidate_id,candidate_name,match_percent,email,phone,linkedin,address\n"
        for it in result.get("items", []):
            yield f'{it["candidate_id"]},"{it["candidate_name"]}",{it["match_percent"]},"{it.get("email") or ""}","{it.get("phone") or ""}","{it.get("linkedin") or ""}","{(it.get("address") or "").replace(chr(10)," ")}"\n'

    return StreamingResponse(_gen(), media_type="text/csv")


@router.post("/{job_id}/communications/preview")
def preview_bulk_communications(
    job_id: int,
    request: Request,
    department: str | None = None,
    min_score: float | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    subject: str | None = None,
    body: str = "",
    db: Session = Depends(get_db),
):
    result = RankingService(db).rank_job(job_id=job_id, department=department, min_score=min_score, q=q, limit=limit, use_cache=False)
    contacts = []
    for it in result.get("items", []):
        if it.get("email") or it.get("phone"):
            contacts.append(
                {
                    "candidate_id": it["candidate_id"],
                    "candidate_name": it["candidate_name"],
                    "email": it.get("email"),
                    "phone": it.get("phone"),
                    "linkedin": it.get("linkedin"),
                }
            )
    AuditService(db).log(
        action="jobs.communications.preview",
        resource_type="job",
        resource_id=str(job_id),
        ip=request.client.host if request.client else None,
        metadata={"count": len(contacts)},
    )
    return {"job_id": job_id, "subject": subject, "body": body, "recipients": contacts}


def _infer_department_from_folders(*, title: str) -> str | None:
    mapped = infer_setor_from_job_title(title)
    if mapped:
        return mapped

    t = _norm(title)
    if not t:
        return None
    settings = get_settings()
    root = settings.recv_dir_path()
    if not root.exists() or not root.is_dir():
        return None
    folders = [p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    best = None
    best_score = 0
    for f in folders:
        fn = _norm(f)
        if not fn:
            continue
        score = _token_overlap(t, fn)
        if score > best_score:
            best_score = score
            best = f
    return best


def _token_overlap(a: str, b: str) -> int:
    ta = set(a.replace("_", " ").split())
    tb = set(b.replace("_", " ").split())
    return len(ta.intersection(tb))


def _norm(s: str) -> str:
    import unicodedata
    s = (s or "").strip().lower()
    if not s:
        return ""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_feedback_signal(app: Application) -> dict:
    # Sinal simples de aprendizado online por critério.
    cargo = 0.8 if app.primary_role else 0.45
    formacao = 0.6 if (app.analysis_json and "formacao" in app.analysis_json.lower()) else 0.4
    cursos = 0.65 if (app.strengths and any(x in app.strengths.lower() for x in ["nr10", "nr35", "cnh", "certific"])) else 0.4
    experiencia = min(1.0, max(0.2, float((app.experience_years or 0.0) / 8.0)))
    return {
        "cargo": cargo,
        "formacao": formacao,
        "cursos": cursos,
        "experiencia": experiencia,
    }


def _parse_iso_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} inválido. Use ISO-8601.") from exc


def _build_ranking_audit_payload(
    *,
    db: Session,
    job: Job,
    decision: str | None,
    application_id: int | None,
    date_from: str | None,
    date_to: str | None,
    q: str | None,
    min_score: float | None,
    limit_events: int,
    snapshot_limit: int,
) -> dict:
    current_profile = read_scoring_profile(job)
    snapshot = RankingService(db).rank_job(
        job_id=job.id,
        department=job.department,
        min_score=min_score,
        q=q,
        limit=snapshot_limit,
        use_cache=False,
    )

    dt_from = _parse_iso_datetime(date_from, field_name="date_from")
    dt_to = _parse_iso_datetime(date_to, field_name="date_to")
    if dt_from and dt_to and dt_from > dt_to:
        raise HTTPException(status_code=422, detail="date_from não pode ser maior que date_to.")

    query = db.query(AuditLog).filter(
        or_(
            AuditLog.action == "jobs.ranking_feedback",
            AuditLog.action == "jobs.ranking_profile.update",
        ),
        AuditLog.resource_type == "job",
        AuditLog.resource_id == str(job.id),
    )
    if dt_from:
        query = query.filter(AuditLog.created_at >= dt_from)
    if dt_to:
        query = query.filter(AuditLog.created_at <= dt_to)
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit_events).all()

    filtered_events = []
    decision_norm = (decision or "").strip().lower()
    for row in rows:
        meta = {}
        if row.metadata_json:
            try:
                meta = json.loads(row.metadata_json)
            except Exception:
                meta = {}
        event_app_id = meta.get("application_id")
        event_decision = str(meta.get("decision") or "").lower()

        if decision_norm and event_decision != decision_norm:
            continue
        if application_id is not None and event_app_id != application_id:
            continue

        action = row.action or ""
        if action == "jobs.ranking_profile.update":
            filtered_events.append(
                {
                    "id": row.id,
                    "created_at": row.created_at.isoformat(),
                    "actor": row.actor,
                    "application_id": None,
                    "decision": "profile_update",
                    "note": "Atualização manual do perfil de score",
                    "before_profile": None,
                    "after_profile": meta if isinstance(meta, dict) else None,
                    "action": action,
                }
            )
            continue

        filtered_events.append(
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "actor": row.actor,
                "application_id": event_app_id,
                "decision": meta.get("decision"),
                "note": meta.get("note"),
                "before_profile": meta.get("before_profile"),
                "after_profile": meta.get("after_profile"),
                "action": action,
            }
        )

    return {
        "job_id": job.id,
        "current_profile": current_profile,
        "feedback_events": filtered_events,
        "ranking_snapshot": snapshot.get("items", []),
    }
