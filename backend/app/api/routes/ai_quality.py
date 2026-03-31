from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.models.application import Application
from app.models.matching_calibration import MatchingCalibration
from app.models.matching_label import MatchingLabel
from app.services.audit import AuditService


router = APIRouter()


class LabelCreate(BaseModel):
    job_id: int
    candidate_id: int
    application_id: int | None = None
    decision: str = Field(max_length=20)
    expected_score: float | None = None
    reviewer: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class CalibrationUpsert(BaseModel):
    job_id: int | None = None
    department: str | None = Field(default=None, max_length=120)
    score_multiplier: float = 1.0
    score_bias: float = 0.0
    min_score_floor: float | None = None
    notes: str | None = None
    updated_by: str | None = Field(default=None, max_length=120)


@router.post("/labels")
def create_label(
    payload: LabelCreate,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    row = MatchingLabel(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    AuditService(db).log(
        action="ai_quality.label.create",
        resource_type="matching_label",
        resource_id=str(row.id),
        ip=request.client.host if request.client else None,
        metadata={"job_id": row.job_id, "decision": row.decision},
    )
    return row


@router.get("/labels")
def list_labels(
    job_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    stmt = select(MatchingLabel).order_by(MatchingLabel.created_at.desc()).limit(max(1, min(limit, 1000)))
    if job_id is not None:
        stmt = stmt.where(MatchingLabel.job_id == job_id)
    return list(db.execute(stmt).scalars().all())


@router.put("/calibration")
def upsert_calibration(
    payload: CalibrationUpsert,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    row = (
        db.execute(
            select(MatchingCalibration).where(
                MatchingCalibration.job_id == payload.job_id,
                MatchingCalibration.department == payload.department,
            )
        )
        .scalars()
        .first()
    )
    if not row:
        row = MatchingCalibration(job_id=payload.job_id, department=payload.department)
    row.score_multiplier = payload.score_multiplier
    row.score_bias = payload.score_bias
    row.min_score_floor = payload.min_score_floor
    row.notes = payload.notes
    row.updated_by = payload.updated_by
    db.add(row)
    db.commit()
    db.refresh(row)
    AuditService(db).log(
        action="ai_quality.calibration.upsert",
        resource_type="matching_calibration",
        resource_id=str(row.id),
        ip=request.client.host if request.client else None,
        metadata={"job_id": row.job_id, "department": row.department},
    )
    return row


@router.get("/calibration")
def list_calibration(
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    return list(db.execute(select(MatchingCalibration).order_by(MatchingCalibration.updated_at.desc())).scalars().all())


@router.get("/evaluation")
def evaluation(
    job_id: int | None = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    label_stmt = select(MatchingLabel)
    if job_id is not None:
        label_stmt = label_stmt.where(MatchingLabel.job_id == job_id)
    labels = list(db.execute(label_stmt).scalars().all())
    if not labels:
        return {"samples": 0, "mae": None, "approval_precision": None, "gain_vs_baseline": None}

    mae_acc = 0.0
    mae_n = 0
    approved_total = 0
    approved_correct = 0
    for row in labels:
        app_score = None
        if row.application_id:
            app = db.get(Application, row.application_id)
            app_score = app.score if app else None
        if row.expected_score is not None and app_score is not None:
            mae_acc += abs(float(row.expected_score) - float(app_score))
            mae_n += 1
        if row.decision == "approved":
            approved_total += 1
            if app_score is not None and app_score >= 70:
                approved_correct += 1

    mae = round(mae_acc / mae_n, 3) if mae_n else None
    precision = round((approved_correct / approved_total) * 100.0, 2) if approved_total else None
    baseline = 55.0
    gain = round((precision - baseline), 2) if precision is not None else None
    return {"samples": len(labels), "mae": mae, "approval_precision": precision, "gain_vs_baseline": gain}


@router.post("/apply-calibration/{application_id}")
def apply_calibration(
    application_id: int,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Candidatura não encontrada")
    job_cal = (
        db.execute(
            select(MatchingCalibration).where(
                MatchingCalibration.job_id == app.job_id,
            )
        )
        .scalars()
        .first()
    )
    if not job_cal:
        return {"status": "no_calibration"}
    score = float(app.score or 0.0)
    adjusted = score * float(job_cal.score_multiplier or 1.0) + float(job_cal.score_bias or 0.0)
    if job_cal.min_score_floor is not None:
        adjusted = max(adjusted, float(job_cal.min_score_floor))
    app.score = round(max(0.0, min(100.0, adjusted)), 2)
    db.add(app)
    db.commit()
    db.refresh(app)
    return {"status": "ok", "application_id": app.id, "adjusted_score": app.score}
