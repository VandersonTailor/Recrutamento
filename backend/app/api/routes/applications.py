import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.common import ApplicationStage
from app.models.job import Job
from app.models.resume import Resume
from app.models.stage_history import StageHistory
from app.repositories.applications import ApplicationRepository
from app.schemas.application import ApplicationCreate, ApplicationOut, ApplicationSLAOut, ApplicationStageUpdate
from app.services.audit import AuditService
from app.services.stage_automation import run_stage_automations


router = APIRouter()
FLOW_STAGES = [
    ApplicationStage.recebido.value,
    ApplicationStage.em_analise.value,
    ApplicationStage.pre_selecionado.value,
    ApplicationStage.entrevista.value,
    ApplicationStage.teste_tecnico.value,
]
ALL_STAGES = FLOW_STAGES + [
    ApplicationStage.banco_talentos.value,
    ApplicationStage.aprovado.value,
    ApplicationStage.reprovado.value,
]
STAGE_SLA_HOURS = {
    ApplicationStage.recebido.value: 24,
    ApplicationStage.em_analise.value: 48,
    ApplicationStage.pre_selecionado.value: 72,
    ApplicationStage.entrevista.value: 120,
    ApplicationStage.teste_tecnico.value: 96,
}


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    request: Request,
    job_id: int | None = None,
    candidate_id: int | None = None,
    channel: str | None = None,
    min_score: float | None = None,
    min_experience_years: float | None = None,
    seniority: str | None = None,
    department: str | None = None,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if job_id:
        stmt = (
            select(Application, Candidate, Job)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .where(Application.job_id == job_id)
            .order_by(Application.score.desc().nullslast(), Application.updated_at.desc())
        )
    else:
        stmt = (
            select(Application, Candidate, Job)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .order_by(Application.updated_at.desc())
            .limit(200)
        )
    if min_score is not None:
        stmt = stmt.where(Application.score.is_not(None), Application.score >= min_score)
    if candidate_id is not None:
        stmt = stmt.where(Application.candidate_id == candidate_id)
    if min_experience_years is not None:
        stmt = stmt.where(Application.experience_years.is_not(None), Application.experience_years >= min_experience_years)
    if seniority:
        stmt = stmt.where(Application.seniority == seniority)
    if channel:
        stmt = stmt.join(Resume, Resume.candidate_id == Application.candidate_id).where(Resume.source_channel == channel)
    if department:
        stmt = stmt.join(Resume, Resume.candidate_id == Application.candidate_id).where(Resume.department == department)
    if date_from:
        try:
            from datetime import datetime
            df = datetime.fromisoformat(date_from)
            stmt = stmt.where(Application.updated_at >= df)
        except Exception:
            pass
    if date_to:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_to)
            stmt = stmt.where(Application.updated_at <= dt)
        except Exception:
            pass
    rows = db.execute(stmt).all()
    app_ids = [app.id for app, _, _ in rows]
    stage_entered_map = _stage_entered_at_map(db=db, app_ids=app_ids)

    out: list[ApplicationOut] = []
    for app, cand, job in rows:
        dto = _build_application_out(app=app, candidate_name=cand.full_name, job_title=job.title, stage_entered_at=stage_entered_map.get(app.id))
        out.append(dto)
    AuditService(db).log(
        action="applications.list",
        ip=request.client.host if request.client else None,
        metadata={"job_id": job_id, "channel": channel, "min_score": min_score},
    )
    return out


@router.get("/sla-alerts", response_model=ApplicationSLAOut)
def list_sla_alerts(
    request: Request,
    job_id: int | None = None,
    only_overdue: bool = False,
    max_items: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Application, Candidate, Job)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Job, Job.id == Application.job_id)
        .order_by(Application.updated_at.desc())
        .limit(max_items)
    )
    if job_id:
        stmt = stmt.where(Application.job_id == job_id)
    rows = db.execute(stmt).all()
    app_ids = [app.id for app, _, _ in rows]
    stage_entered_map = _stage_entered_at_map(db=db, app_ids=app_ids)

    items: list[ApplicationOut] = []
    overdue_count = 0
    due_soon_count = 0
    for app, cand, job in rows:
        dto = _build_application_out(app=app, candidate_name=cand.full_name, job_title=job.title, stage_entered_at=stage_entered_map.get(app.id))
        if dto.stage_overdue:
            overdue_count += 1
        if dto.stage_sla_hours and not dto.stage_overdue and dto.stage_elapsed_hours is not None:
            remaining = dto.stage_sla_hours - dto.stage_elapsed_hours
            if 0 <= remaining <= 8:
                due_soon_count += 1
        if only_overdue and not dto.stage_overdue:
            continue
        items.append(dto)

    AuditService(db).log(
        action="applications.sla_alerts",
        ip=request.client.host if request.client else None,
        metadata={"job_id": job_id, "only_overdue": only_overdue, "overdue_count": overdue_count, "due_soon_count": due_soon_count},
    )
    return {
        "total_in_scope": len(rows),
        "overdue_count": overdue_count,
        "due_soon_count": due_soon_count,
        "items": items,
    }


@router.post("", response_model=ApplicationOut)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)):
    repo = ApplicationRepository(db)
    existing = repo.get_by_candidate_job(candidate_id=payload.candidate_id, job_id=payload.job_id)
    if existing:
        raise HTTPException(status_code=409, detail="Candidatura já existe para candidato/vaga")
    app = repo.create(Application(candidate_id=payload.candidate_id, job_id=payload.job_id))
    db.add(StageHistory(application_id=app.id, from_stage=None, to_stage=app.stage, note="Criada manualmente"))
    db.commit()
    out = ApplicationOut.model_validate(app)
    out.secondary_roles = _safe_roles(app.secondary_roles_json)
    return out


@router.patch("/{application_id}/stage", response_model=ApplicationOut)
def move_stage(application_id: int, payload: ApplicationStageUpdate, request: Request, db: Session = Depends(get_db)):
    repo = ApplicationRepository(db)
    app = repo.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")
    _validate_stage(payload.to_stage)
    from_stage = app.stage
    app.stage = payload.to_stage
    repo.update(app)
    db.add(StageHistory(application_id=app.id, from_stage=from_stage, to_stage=payload.to_stage, note=payload.note))
    db.commit()
    AuditService(db).log(
        action="applications.move_stage",
        resource_type="application",
        resource_id=str(application_id),
        ip=request.client.host if request.client else None,
        metadata={"from": from_stage, "to": payload.to_stage},
    )
    out = ApplicationOut.model_validate(app)
    out.secondary_roles = _safe_roles(app.secondary_roles_json)
    return out


@router.post("/{application_id}/advance", response_model=ApplicationOut)
def advance_stage(application_id: int, request: Request, note: str | None = None, db: Session = Depends(get_db)):
    repo = ApplicationRepository(db)
    app = repo.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")

    if app.stage in (ApplicationStage.aprovado.value, ApplicationStage.reprovado.value):
        raise HTTPException(status_code=409, detail="Candidatura já finalizada. Use banco de talentos para reabrir.")

    if app.stage == ApplicationStage.banco_talentos.value:
        to_stage = ApplicationStage.recebido.value
    else:
        try:
            idx = FLOW_STAGES.index(app.stage)
            to_stage = FLOW_STAGES[min(idx + 1, len(FLOW_STAGES) - 1)]
        except ValueError:
            to_stage = ApplicationStage.em_analise.value

    return _apply_stage_change(
        app=app,
        to_stage=to_stage,
        note=note or "Avanço para próxima etapa",
        action="applications.advance",
        request=request,
        db=db,
        repo=repo,
    )


@router.post("/{application_id}/approve", response_model=ApplicationOut)
def approve_application(application_id: int, request: Request, note: str | None = None, db: Session = Depends(get_db)):
    repo = ApplicationRepository(db)
    app = repo.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")
    return _apply_stage_change(
        app=app,
        to_stage=ApplicationStage.aprovado.value,
        note=note or "Candidato aprovado",
        action="applications.approve",
        request=request,
        db=db,
        repo=repo,
    )


@router.post("/{application_id}/dismiss", response_model=ApplicationOut)
def dismiss_application(application_id: int, request: Request, note: str | None = None, db: Session = Depends(get_db)):
    repo = ApplicationRepository(db)
    app = repo.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")
    return _apply_stage_change(
        app=app,
        to_stage=ApplicationStage.reprovado.value,
        note=note or "Candidato dispensado",
        action="applications.dismiss",
        request=request,
        db=db,
        repo=repo,
    )


@router.post("/{application_id}/talent-pool", response_model=ApplicationOut)
def move_to_talent_pool(application_id: int, request: Request, note: str | None = None, db: Session = Depends(get_db)):
    repo = ApplicationRepository(db)
    app = repo.get(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")
    return _apply_stage_change(
        app=app,
        to_stage=ApplicationStage.banco_talentos.value,
        note=note or "Movido para banco de talentos",
        action="applications.talent_pool",
        request=request,
        db=db,
        repo=repo,
    )


def _apply_stage_change(
    *,
    app: Application,
    to_stage: str,
    note: str | None,
    action: str,
    request: Request,
    db: Session,
    repo: ApplicationRepository,
) -> ApplicationOut:
    _validate_stage(to_stage)
    from_stage = app.stage
    app.stage = to_stage
    repo.update(app)
    db.add(StageHistory(application_id=app.id, from_stage=from_stage, to_stage=to_stage, note=note))
    db.commit()
    try:
        run_stage_automations(db=db, application_id=app.id, from_stage=from_stage, to_stage=to_stage)
    except Exception:
        pass
    AuditService(db).log(
        action=action,
        resource_type="application",
        resource_id=str(app.id),
        ip=request.client.host if request.client else None,
        metadata={"from": from_stage, "to": to_stage},
    )
    return _build_application_out(app=app, candidate_name=None, job_title=None, stage_entered_at=datetime.now(timezone.utc).replace(tzinfo=None))


def _safe_roles(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data[:5]]
    except Exception:
        return []
    return []


def _validate_stage(stage: str) -> None:
    if stage not in ALL_STAGES:
        raise HTTPException(status_code=422, detail="Etapa inválida para candidatura.")


def _stage_entered_at_map(*, db: Session, app_ids: list[int]) -> dict[int, datetime]:
    if not app_ids:
        return {}
    rows = (
        db.execute(
            select(StageHistory)
            .where(StageHistory.application_id.in_(app_ids))
            .order_by(StageHistory.changed_at.desc())
        )
        .scalars()
        .all()
    )
    latest_by_pair: dict[tuple[int, str], datetime] = {}
    for row in rows:
        key = (row.application_id, row.to_stage)
        if key not in latest_by_pair:
            latest_by_pair[key] = row.changed_at
    out: dict[int, datetime] = {}
    for app_id, stage in latest_by_pair:
        if app_id not in out:
            out[app_id] = latest_by_pair[(app_id, stage)]
    return out


def _compute_stage_sla(stage: str, *, stage_entered_at: datetime | None) -> tuple[int | None, int | None, bool | None, int | None]:
    sla = STAGE_SLA_HOURS.get(stage)
    if sla is None or stage_entered_at is None:
        return (None, None, None, None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    elapsed = max(0, int((now - stage_entered_at).total_seconds() // 3600))
    overdue = elapsed > sla
    overdue_hours = max(0, elapsed - sla)
    return (sla, elapsed, overdue, overdue_hours)


def _build_application_out(
    *,
    app: Application,
    candidate_name: str | None,
    job_title: str | None,
    stage_entered_at: datetime | None,
) -> ApplicationOut:
    dto = ApplicationOut.model_validate(app)
    dto.candidate_name = candidate_name
    dto.job_title = job_title
    dto.secondary_roles = _safe_roles(app.secondary_roles_json)
    entered = stage_entered_at or app.updated_at or app.created_at
    dto.stage_entered_at = entered
    sla, elapsed, overdue, overdue_hours = _compute_stage_sla(app.stage, stage_entered_at=entered)
    dto.stage_sla_hours = sla
    dto.stage_elapsed_hours = elapsed
    dto.stage_overdue = overdue
    dto.stage_overdue_hours = overdue_hours
    return dto
