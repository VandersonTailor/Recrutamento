from pathlib import Path
import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import RequireApiKey
from app.models.candidate import Candidate
from app.models.application import Application
from app.models.job import Job
from app.models.stage_history import StageHistory
from app.models.resume import Resume
from app.models.resume_change_history import ResumeChangeHistory
from app.models.common import ApplicationStage
from app.schemas.resume import ResumeDetail, ResumeOut, ResumeStructuredUpdate
from app.schemas.resume import ResumeFileUpdate, ResumeHistoryOut, ResumeDivergenceOut
from app.services.audit import AuditService
from app.services.resume_view import (
    build_professional_summary,
    extract_address,
    extract_email,
    extract_linkedin,
    extract_phone,
    is_address_plausible,
    validate_contact,
)
from app.models.resume_file import ResumeFile
from app.services.text_extraction import extract_text
from app.services.ai import analyze_resume
from app.services.resume_structuring import structure_resume_text
from app.services.cargo_taxonomy import apply_role_feedback, get_role_feedback_profile
from app.repositories.applications import ApplicationRepository
from app.repositories.jobs import JobRepository
from app.repositories.resumes import ResumeRepository
from app.repositories.departments import DepartmentRepository
from app.services.resume_file_naming import build_resume_filename
from app.services.resume_file_naming import parse_resume_filename


router = APIRouter()


def _talent_pool_candidate_subquery():
    # Robustez para pequenas variações de escrita do estágio.
    # Ex.: "Banco de talentos", "banco talentos", etc.
    stage_norm = func.lower(Application.stage)
    return select(Application.candidate_id).where(
        stage_norm.like("%banco%")
    ).where(
        stage_norm.like("%talent%")
    )


def _candidate_current_stage_map(*, db: Session, candidate_ids: list[int]) -> dict[int, str]:
    if not candidate_ids:
        return {}
    rows = db.execute(
        select(Application.candidate_id, Application.stage, Application.updated_at, Application.created_at)
        .where(Application.candidate_id.in_(candidate_ids))
        .order_by(
            Application.candidate_id.asc(),
            Application.updated_at.desc(),
            Application.created_at.desc(),
            Application.id.desc(),
        )
    ).all()
    out: dict[int, str] = {}
    for candidate_id, stage, _updated_at, _created_at in rows:
        if candidate_id in out:
            continue
        out[candidate_id] = stage
    return out


def _is_structured_empty(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    try:
        parsed = json.loads(raw)
    except Exception:
        return True
    if not isinstance(parsed, dict) or not parsed:
        return True
    fields = parsed.get("fields")
    quality = parsed.get("quality")
    return not isinstance(fields, dict) or not fields or not isinstance(quality, dict)


def _extract_city_from_structured_json(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return _extract_city_from_structured_dict(parsed)


def _extract_city_from_structured_dict(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return None
    city = fields.get("cidade_regiao")
    if not isinstance(city, str):
        return None
    city = city.strip()
    if not city:
        return None
    return city[:120]


def _norm_cargo(value: str | None) -> str:
    raw = (value or "").strip().lower()
    raw = raw.replace("_", " ").replace("-", " ")
    raw = " ".join(raw.split())
    return raw


def _is_placeholder_name(value: str | None) -> bool:
    raw = (value or "").strip().lower()
    raw = raw.replace("_", " ")
    raw = " ".join(raw.split())
    if raw in {"", "semnome", "sem nome", "desconhecido", "nao informado", "não informado", "semnome"}:
        return True
    noisy_fragments = (
        "titulo de eleitor",
        "objetivo",
        "perfil profissional",
        "primeiro emprego",
        "experiencia",
        "atendente",
        "operador",
        "padaria",
        "empacotadora",
    )
    return any(frag in raw for frag in noisy_fragments)


def _compute_divergence(resume: Resume, *, min_confidence: float = 0.6) -> dict | None:
    filename_cargo = _norm_cargo(resume.filename_cargo)
    if not resume.structured_json:
        return None
    try:
        data = json.loads(resume.structured_json)
    except Exception:
        return None
    fields = data.get("fields") if isinstance(data, dict) else None
    quality = data.get("quality") if isinstance(data, dict) else None
    if not isinstance(fields, dict):
        return None
    role = fields.get("classificacao_cargo")
    if not isinstance(role, dict):
        return None
    suggested = _norm_cargo(role.get("primary_role"))
    conf = role.get("confidence")
    try:
        confidence = float(conf)
    except Exception:
        confidence = 0.0
    if confidence < min_confidence:
        return None

    sem_cargo_like = filename_cargo in {"", "sem cargo", "outros", "sem_cargo"}
    if sem_cargo_like and suggested:
        return {"suggested_cargo": role.get("primary_role"), "confidence": confidence, "reason": "arquivo_sem_cargo"}

    if suggested and filename_cargo and suggested != filename_cargo:
        return {"suggested_cargo": role.get("primary_role"), "confidence": confidence, "reason": "cargo_divergente"}

    needs_review = bool((quality or {}).get("role_classification_needs_review")) if isinstance(quality, dict) else False
    if needs_review:
        return {
            "suggested_cargo": role.get("primary_role"),
            "confidence": confidence,
            "reason": (quality or {}).get("role_review_reason") if isinstance(quality, dict) else "revisao_necessaria",
        }
    return None


def _has_role_divergence(resume: Resume) -> bool:
    return _compute_divergence(resume, min_confidence=0.55) is not None


@router.get("/classification/profile")
def get_classification_profile(
    request: Request,
    db: Session = Depends(get_db),
):
    profile = get_role_feedback_profile()
    AuditService(db).log(
        action="resumes.classification.profile",
        ip=request.client.host if request.client else None,
        metadata={"total_feedback": (profile.get("stats") or {}).get("total_feedback", 0)},
    )
    return profile

@router.get("/files")
def list_storage_files(
    request: Request,
    limit: int = 200,
    offset: int = 0,
    ext: str | None = Query(default=None, description="Ex: pdf, docx"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    root = settings.recv_dir_path()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"recv_dir não encontrado ou inacessível: {root}")

    allowed_exts = {".pdf", ".docx", ".doc", ".rtf", ".txt", ".jpg", ".png"}
    if ext:
        allowed_exts = {"." + ext.lower().lstrip(".")}

    all_files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() not in allowed_exts:
            continue
        all_files.append(p)

    all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    slice_files = all_files[offset : offset + limit]

    AuditService(db).log(action="storage.list_files", ip=request.client.host if request.client else None, metadata={"ext": ext})
    return {
        "root": str(root),
        "count": len(all_files),
        "items": [{"path": str(p), "name": p.name} for p in slice_files],
    }


@router.get("", response_model=list[ResumeOut])
def list_resumes(
    request: Request,
    department: str | None = Query(default=None, description="Nome da pasta/departamento (ex: motorista, jovem_aprendiz)"),
    candidate_id: int | None = None,
    q: str | None = Query(default=None, description="Busca simples no nome do candidato"),
    cargo: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    include_missing: bool = False,
    requires_review: bool | None = Query(default=None),
    divergence_only: bool = Query(default=False),
    talent_pool_only: bool = Query(default=False),
    include_talent_pool: bool = Query(default=False),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Resume, Candidate).join(Candidate, Candidate.id == Resume.candidate_id)
    if not department and q:
        department = _infer_department_from_query(q)
    if not include_missing:
        stmt = stmt.where(Resume.missing_in_storage.is_(False))
    if department:
        stmt = stmt.where(Resume.department == department)
    if candidate_id:
        stmt = stmt.where(Resume.candidate_id == candidate_id)
    if requires_review is not None:
        stmt = stmt.where(Resume.requires_manual_review.is_(requires_review))
    talent_subq = _talent_pool_candidate_subquery()
    if talent_pool_only:
        stmt = stmt.where(Resume.candidate_id.in_(talent_subq))
    elif not include_talent_pool:
        stmt = stmt.where(~Resume.candidate_id.in_(talent_subq))
    if q:
        stmt = stmt.where(Candidate.full_name.ilike(f"%{q}%"))
    if cargo:
        stmt = stmt.where(
            or_(
                Resume.original_filename.ilike(f"%{cargo}%"),
                Resume.filename_cargo.ilike(f"%{cargo}%"),
            )
        )
    if from_date:
        try:
            from datetime import datetime
            fd = datetime.fromisoformat(from_date)
            stmt = stmt.where(Resume.received_at >= fd)
        except Exception:
            pass
    if to_date:
        try:
            from datetime import datetime
            td = datetime.fromisoformat(to_date)
            stmt = stmt.where(Resume.received_at <= td)
        except Exception:
            pass
    stmt = stmt.order_by(Resume.received_at.desc()).offset(offset).limit(limit)
    rows = db.execute(stmt).all()
    candidate_ids = [cand.id for _resume, cand in rows]
    stage_map = _candidate_current_stage_map(db=db, candidate_ids=candidate_ids)
    out: list[ResumeOut] = []
    for resume, cand in rows:
        fp = Path(resume.file_path)
        if not fp.exists():
            if not resume.missing_in_storage:
                try:
                    resume.missing_in_storage = True
                    resume.missing_at = datetime.utcnow()
                    db.add(resume)
                    db.commit()
                except Exception:
                    db.rollback()
            if not include_missing:
                continue
        if not resume.department:
            dep = _infer_department_from_path(resume.file_path)
            if dep:
                try:
                    resume.department = dep
                    db.add(resume)
                    db.commit()
                except Exception:
                    db.rollback()
        dto = ResumeOut.model_validate(resume)
        dto.candidate_name = cand.full_name
        dto.current_stage = stage_map.get(cand.id)
        if divergence_only and not _has_role_divergence(resume):
            continue
        out.append(dto)

    AuditService(db).log(
        action="resumes.list",
        ip=request.client.host if request.client else None,
        metadata={
            "q": q,
            "department": department,
            "include_missing": include_missing,
            "requires_review": requires_review,
            "talent_pool_only": talent_pool_only,
            "include_talent_pool": include_talent_pool,
        },
    )
    return out


@router.get("/divergences", response_model=list[ResumeDivergenceOut])
def list_resume_divergences(
    request: Request,
    department: str | None = Query(default=None),
    limit: int = 100,
    offset: int = 0,
    min_confidence: float = Query(default=0.6, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Resume, Candidate)
        .join(Candidate, Candidate.id == Resume.candidate_id)
        .where(Resume.missing_in_storage.is_(False))
        .order_by(Resume.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if department:
        stmt = stmt.where(Resume.department == department)
    rows = db.execute(stmt).all()
    out: list[ResumeDivergenceOut] = []
    for resume, cand in rows:
        divergence = _compute_divergence(resume, min_confidence=min_confidence)
        if not divergence:
            continue
        out.append(
            ResumeDivergenceOut(
                resume_id=resume.id,
                candidate_id=resume.candidate_id,
                candidate_name=cand.full_name,
                file_name=resume.original_filename,
                department=resume.department,
                filename_cargo=resume.filename_cargo,
                suggested_cargo=divergence.get("suggested_cargo"),
                suggestion_confidence=divergence.get("confidence"),
                reason=divergence.get("reason", "divergencia"),
                requires_review=resume.requires_manual_review or True,
            )
        )
    AuditService(db).log(
        action="resumes.divergences",
        ip=request.client.host if request.client else None,
        metadata={"department": department, "count": len(out), "min_confidence": min_confidence},
    )
    return out


@router.get("/review-queue", response_model=list[ResumeOut])
def list_review_queue(
    request: Request,
    department: str | None = Query(default=None),
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Resume, Candidate)
        .join(Candidate, Candidate.id == Resume.candidate_id)
        .where(Resume.requires_manual_review.is_(True), Resume.missing_in_storage.is_(False))
        .order_by(Resume.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if department:
        stmt = stmt.where(Resume.department == department)

    rows = db.execute(stmt).all()
    out: list[ResumeOut] = []
    for resume, cand in rows:
        dto = ResumeOut.model_validate(resume)
        dto.candidate_name = cand.full_name
        out.append(dto)

    AuditService(db).log(
        action="resumes.review_queue",
        ip=request.client.host if request.client else None,
        metadata={"department": department, "limit": limit},
    )
    return out


@router.post("/actions/cleanup_missing")
def cleanup_missing_action(request: Request, db: Session = Depends(get_db)):
    updated = 0
    for resume in db.execute(select(Resume).where(Resume.missing_in_storage.is_(False))).scalars().all():
        if not Path(resume.file_path).exists():
            resume.missing_in_storage = True
            resume.missing_at = datetime.utcnow()
            db.add(resume)
            updated += 1
    db.commit()
    AuditService(db).log(action="resumes.cleanup_missing", ip=request.client.host if request.client else None, metadata={"updated": updated})
    return {"status": "ok", "updated": updated}


@router.post("/actions/backfill_structured")
def backfill_structured_action(
    request: Request,
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(
            select(Resume, Candidate)
            .join(Candidate, Candidate.id == Resume.candidate_id)
            .order_by(Resume.id.asc())
            .limit(limit)
        )
        .all()
    )

    processed = 0
    updated = 0
    skipped = 0
    errors = 0
    error_samples: list[dict] = []

    for resume, cand in rows:
        processed += 1
        if not _is_structured_empty(resume.structured_json):
            skipped += 1
            continue

        try:
            parsed_filename = parse_resume_filename(resume.original_filename or Path(resume.file_path).name)
            if not resume.filename_cargo:
                resume.filename_cargo = parsed_filename.get("cargo")
            if not resume.filename_cnh:
                resume.filename_cnh = parsed_filename.get("cnh")
            if not resume.filename_date:
                resume.filename_date = parsed_filename.get("data")
            text = (resume.extracted_text or "").strip()
            if not text:
                try:
                    extracted = extract_text(Path(resume.file_path))
                    text = (extracted or "").strip()
                    if text:
                        resume.extracted_text = extracted
                except Exception:
                    text = ""

            if not text:
                skipped += 1
                continue

            structured = structure_resume_text(text=text, fallback_name=cand.full_name)
            resume.structured_json = json.dumps(structured, ensure_ascii=False)
            resume.extraction_confidence = structured.get("quality", {}).get("confidence")
            resume.requires_manual_review = bool(structured.get("quality", {}).get("requires_manual_review"))
            resume.review_reason = structured.get("quality", {}).get("review_reason")
            db.add(resume)

            # Atualiza endereço se o atual for inválido
            extracted_address = extract_address(text)
            fallback_city = _extract_city_from_structured_dict(structured)
            resolved_address = extracted_address or fallback_city
            if resolved_address and (not cand.address or not is_address_plausible(cand.address)):
                cand.address = resolved_address
                db.add(cand)

            db.commit()
            _sync_role_classification_to_applications(db=db, candidate_id=resume.candidate_id, structured_json=structured)
            updated += 1
        except Exception as exc:
            db.rollback()
            errors += 1
            if len(error_samples) < 20:
                error_samples.append({"resume_id": resume.id, "candidate_id": resume.candidate_id, "error": str(exc)})

    result = {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_samples": error_samples,
    }
    AuditService(db).log(
        action="resumes.backfill_structured",
        ip=request.client.host if request.client else None,
        metadata=result,
    )
    return result


def _infer_department_from_path(file_path: str) -> str | None:
    settings = get_settings()
    root = settings.recv_dir_path()
    try:
        rel = Path(file_path).resolve().relative_to(root.resolve())
    except Exception:
        try:
            fp = str(file_path).replace("/", "\\")
            rr = str(root).rstrip("\\")
            if fp.lower().startswith(rr.lower() + "\\"):
                rel_s = fp[len(rr) + 1 :]
                first = rel_s.split("\\", 1)[0]
                return first or None
        except Exception:
            return None
        return None
    if not rel.parts:
        return None
    return rel.parts[0]


def _infer_department_from_query(query: str) -> str | None:
    settings = get_settings()
    root = settings.recv_dir_path()
    if not root.exists() or not root.is_dir():
        return None
    qn = _norm(query)
    if not qn:
        return None
    for p in root.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        dn = _norm(p.name)
        if dn == qn or dn.replace("_", " ") == qn or qn in dn.replace("_", " "):
            return p.name
    return None


def _norm(s: str) -> str:
    import unicodedata
    import re
    s = (s or "").strip().lower()
    if not s:
        return ""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_young_apprentice_label(value: str | None) -> bool:
    n = _norm(value or "")
    return ("jovem aprendiz" in n) or ("menor aprendiz" in n) or ("aprendiz" in n)


def _has_senior_signals(text: str | None) -> bool:
    raw = text or ""
    n = _norm(raw)
    if not n:
        return False
    internship_hints = (
        "estagio",
        "estagiario",
        "estagiaria",
        "aprendizagem",
        "jovem aprendiz",
        "menor aprendiz",
    )
    has_internship_profile = any(k in n for k in internship_hints)
    strong = (
        "chapeador",
        "pintor",
        "motorista",
        "mecanico",
        "eletricista",
        "almoxarife",
        "encarregado",
        "supervisor",
        "marcopolo",
        "restinga transportes",
    )
    has_strong_role = any(k in n for k in strong)
    if has_strong_role:
        return True
    years = re.findall(r"\b(?:19|20)\d{2}\b", raw)
    company_signals = len(re.findall(r"\bempresa\b", n))
    # Histórico de estágio isolado não deve ser tratado como perfil sênior.
    if has_internship_profile and len(years) < 6 and company_signals < 3:
        return False
    if len(years) >= 4:
        return True
    if company_signals >= 2:
        return True
    return False


def _has_apprentice_signals(text: str | None) -> bool:
    n = _norm(text or "")
    if not n:
        return False
    hints = (
        "jovem aprendiz",
        "menor aprendiz",
        "primeiro emprego",
        "sem experiencia",
        "estudante",
        "estagio",
        "estagiario",
        "estagiaria",
        "aprendizagem",
    )
    return any(h in n for h in hints)


def _extract_primary_role(structured_json: str | None) -> tuple[str | None, float | None]:
    if not structured_json:
        return (None, None)
    try:
        data = json.loads(structured_json)
    except Exception:
        return (None, None)
    fields = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, dict):
        return (None, None)
    role = fields.get("classificacao_cargo")
    if not isinstance(role, dict):
        return (None, None)
    primary = role.get("primary_role")
    confidence = role.get("confidence")
    conf = float(confidence) if isinstance(confidence, (int, float)) else None
    primary_name = primary.strip() if isinstance(primary, str) and primary.strip() else None
    return (primary_name, conf)


def _infer_role_from_text(text: str | None) -> str | None:
    n = _norm(text or "")
    if not n:
        return None
    if any(k in n for k in ("chapeador", "pintor", "funilaria", "oficina", "mecanic", "eletric", "preparador")):
        return "Manutencao"
    if any(k in n for k in ("motorista", "condutor", "onibus", "frota", "cnh d", "cnh e")):
        return "Motorista"
    if any(k in n for k in ("administrativo", "assistente administrativo", "office", "excel", "departamento pessoal")):
        return "Administrativo"
    if any(k in n for k in ("atendimento", "atendente", "cliente", "recepcao")):
        return "Atendimento"
    return None


def _find_matching_job(db: Session, role_name: str | None) -> Job | None:
    if not role_name:
        return None
    role_norm = _norm(role_name)
    if not role_norm:
        return None
    jobs = db.execute(select(Job).where(Job.deleted.is_(False))).scalars().all()
    exact = next((j for j in jobs if _norm(j.title) == role_norm), None)
    if exact:
        return exact
    if len(role_norm) <= 2:
        return None
    role_tokens = set(role_norm.split())
    partial = []
    for j in jobs:
        title_norm = _norm(j.title)
        title_tokens = set(title_norm.split())
        if role_norm in title_norm or title_norm in role_norm:
            partial.append(j)
            continue
        if role_tokens and title_tokens and role_tokens.issubset(title_tokens):
            partial.append(j)
    return partial[0] if partial else None


@router.get("/export")
def export_resumes_csv(
    request: Request,
    candidate_id: int | None = None,
    q: str | None = Query(default=None),
    cargo: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Resume, Candidate).join(Candidate, Candidate.id == Resume.candidate_id)
    stmt = stmt.where(Resume.missing_in_storage.is_(False))
    if candidate_id:
        stmt = stmt.where(Resume.candidate_id == candidate_id)
    if q:
        stmt = stmt.where(Candidate.full_name.ilike(f"%{q}%"))
    if cargo:
        stmt = stmt.where(Resume.original_filename.ilike(f"%{cargo}%"))
    rows = db.execute(stmt).all()
    AuditService(db).log(action="resumes.export", ip=request.client.host if request.client else None, metadata={"q": q, "cargo": cargo})
    def _gen():
        yield "id,candidate_name,original_filename,received_at,file_path\n"
        for resume, cand in rows:
            yield f'{resume.id},"{cand.full_name or ""}","{resume.original_filename or ""}",{resume.received_at.isoformat()},"{resume.file_path}"\n'
    return StreamingResponse(_gen(), media_type="text/csv")


@router.get("/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: int, request: Request, db: Session = Depends(get_db)):
    stmt = select(Resume, Candidate).join(Candidate, Candidate.id == Resume.candidate_id).where(Resume.id == resume_id)
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail="Currículo não encontrado")
    resume, cand = row
    if not (resume.filename_cargo and resume.filename_date):
        parsed_filename = parse_resume_filename(resume.original_filename or Path(resume.file_path).name)
        changed = False
        if not resume.filename_cargo and parsed_filename.get("cargo"):
            resume.filename_cargo = parsed_filename.get("cargo")
            changed = True
        if not resume.filename_cnh and parsed_filename.get("cnh"):
            resume.filename_cnh = parsed_filename.get("cnh")
            changed = True
        if not resume.filename_date and parsed_filename.get("data"):
            resume.filename_date = parsed_filename.get("data")
            changed = True
        if changed:
            db.add(resume)
            db.commit()
            db.refresh(resume)
    # lazy enrich: garante texto extraído e estrutura JSON mesmo para currículos antigos
    text = resume.extracted_text or ""
    if not text.strip():
        try:
            extracted = extract_text(Path(resume.file_path))
            if extracted and extracted.strip():
                text = extracted
                resume.extracted_text = extracted
                db.add(resume)
                db.commit()
                db.refresh(resume)
        except Exception:
            db.rollback()
            text = resume.extracted_text or ""

    if _is_structured_empty(resume.structured_json) and text.strip():
        try:
            structured = structure_resume_text(text=text, fallback_name=cand.full_name)
            resume.structured_json = json.dumps(structured, ensure_ascii=False)
            resume.extraction_confidence = structured.get("quality", {}).get("confidence")
            resume.requires_manual_review = bool(structured.get("quality", {}).get("requires_manual_review"))
            resume.review_reason = structured.get("quality", {}).get("review_reason")
            db.add(resume)
            db.commit()
            db.refresh(resume)
        except Exception:
            db.rollback()

    try:
        parsed_structured = json.loads(resume.structured_json or "{}")
    except Exception:
        parsed_structured = {}
    structured_name = None
    if isinstance(parsed_structured, dict):
        structured_name = ((parsed_structured.get("fields", {}) or {}).get("nome"))
    filename_name = parse_resume_filename(resume.original_filename or Path(resume.file_path).name).get("nome")
    if _is_placeholder_name(cand.full_name):
        candidate_name = None
        if isinstance(filename_name, str) and filename_name.strip() and not _is_placeholder_name(filename_name):
            candidate_name = filename_name.strip()
        elif isinstance(structured_name, str) and structured_name.strip() and not _is_placeholder_name(structured_name):
            candidate_name = structured_name.strip()
        if candidate_name:
            cand.full_name = candidate_name
            db.add(cand)
            db.commit()
            db.refresh(cand)

    dto = ResumeDetail.model_validate(resume)
    dto.candidate_name = cand.full_name

    email = cand.email or extract_email(text)
    phone = cand.phone or extract_phone(text)
    extracted_address = extract_address(text)
    structured_city = _extract_city_from_structured_json(resume.structured_json)
    stored_address = cand.address if is_address_plausible(cand.address) else None
    address = stored_address or extracted_address or structured_city
    linkedin = cand.linkedin or extract_linkedin(text)

    dto.candidate_email = email
    dto.candidate_phone = phone
    dto.candidate_address = address
    dto.candidate_linkedin = linkedin
    dto.professional_summary = build_professional_summary(text)
    dto.warnings = validate_contact(email, phone)

    resolved_new_address = extracted_address or structured_city
    should_update_address = bool(resolved_new_address and (not cand.address or not is_address_plausible(cand.address)))
    if (email and not cand.email) or (phone and not cand.phone) or should_update_address or (linkedin and not cand.linkedin):
        try:
            if email and not cand.email:
                cand.email = email
            if phone and not cand.phone:
                cand.phone = phone
            if should_update_address:
                cand.address = resolved_new_address
            if linkedin and not cand.linkedin:
                cand.linkedin = linkedin
            db.add(cand)
            db.commit()
            db.refresh(cand)
            dto.candidate_address = cand.address or address
        except Exception:
            db.rollback()

    AuditService(db).log(action="resumes.get", resource_type="resume", resource_id=str(resume_id), ip=request.client.host if request.client else None)
    return dto


@router.get("/{resume_id}/raw", dependencies=[RequireApiKey])
def get_resume_raw(resume_id: int, request: Request, db: Session = Depends(get_db)):
    rf = db.query(ResumeFile).filter(ResumeFile.resume_id == resume_id).first()
    if not rf:
        raise HTTPException(status_code=404, detail="Arquivo binário não encontrado no banco")
    AuditService(db).log(action="resumes.raw", resource_type="resume", resource_id=str(resume_id), ip=request.client.host if request.client else None, metadata={"bytes": rf.size_bytes})
    def _gen():
        yield rf.content
    return StreamingResponse(_gen(), media_type=rf.mime_type or "application/octet-stream")


@router.post("/{resume_id}/reanalyze")
def reanalyze_resume(resume_id: int, request: Request, db: Session = Depends(get_db)):
    repo_r = ResumeRepository(db)
    resume = repo_r.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Currículo não encontrado")
    try:
        parsed_filename = parse_resume_filename(resume.original_filename or Path(resume.file_path).name)
        text = extract_text(Path(resume.file_path))
        resume.extracted_text = text or resume.extracted_text
        structured = structure_resume_text(
            text=resume.extracted_text or "",
            fallback_name=parsed_filename.get("nome"),
        )
        resume.structured_json = json.dumps(structured, ensure_ascii=False)
        resume.filename_cargo = resume.filename_cargo or parsed_filename.get("cargo")
        resume.filename_cnh = resume.filename_cnh or parsed_filename.get("cnh")
        resume.filename_date = resume.filename_date or parsed_filename.get("data")
        resume.extraction_confidence = structured.get("quality", {}).get("confidence")
        resume.requires_manual_review = bool(structured.get("quality", {}).get("requires_manual_review"))
        resume.review_reason = structured.get("quality", {}).get("review_reason")
        db.add(resume)
        db.commit()

        cand = db.get(Candidate, resume.candidate_id)
        if cand:
            extracted_address = extract_address(resume.extracted_text or "")
            fallback_city = _extract_city_from_structured_dict(structured)
            resolved_address = extracted_address or fallback_city
            if resolved_address and (not cand.address or not is_address_plausible(cand.address)):
                cand.address = resolved_address
                db.add(cand)
                db.commit()

        _sync_role_classification_to_applications(db=db, candidate_id=resume.candidate_id, structured_json=structured)
        job_repo = JobRepository(db)
        apps = db.query(Application).filter(Application.candidate_id == resume.candidate_id).all()
        for app in apps:
            job = job_repo.get(app.job_id)
            if job:
                analysis = analyze_resume(
                    resume_text=resume.extracted_text or "",
                    job_title=job.title,
                    job_description=job.description,
                    job_requirements=job.requirements,
                )
                app.score = analysis.score_aderencia
                app.score_justification = analysis.justificativa_score
                db.add(app)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Falha ao reprocessar currículo: {exc}")

    AuditService(db).log(action="resumes.reanalyze", resource_type="resume", resource_id=str(resume_id), ip=request.client.host if request.client else None)
    return {"status": "ok"}


@router.patch("/{resume_id}/structured", response_model=ResumeDetail)
def update_structured_resume(
    resume_id: int,
    payload: ResumeStructuredUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    stmt = select(Resume, Candidate).join(Candidate, Candidate.id == Resume.candidate_id).where(Resume.id == resume_id)
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail="Currículo não encontrado")
    resume, cand = row

    old_structured = {}
    if resume.structured_json:
        try:
            old_structured = json.loads(resume.structured_json)
        except Exception:
            old_structured = {}

    resume.structured_json = json.dumps(payload.structured_json or {}, ensure_ascii=False)
    if payload.extraction_confidence is not None:
        resume.extraction_confidence = max(0.0, min(1.0, float(payload.extraction_confidence)))
    if payload.approve_review:
        resume.requires_manual_review = False
        resume.review_reason = payload.review_reason
    else:
        resume.requires_manual_review = True
        resume.review_reason = payload.review_reason or "Aguardando revisão manual"
    db.add(resume)
    db.commit()
    _sync_role_classification_to_applications(db=db, candidate_id=resume.candidate_id, structured_json=payload.structured_json or {})

    learning_profile = None
    if payload.approve_review:
        old_role, _, _ = _extract_role_classification(old_structured)
        new_role, _, _ = _extract_role_classification(payload.structured_json or {})
        if new_role:
            learning_profile = apply_role_feedback(correct_role=new_role, predicted_role=old_role)

    db.refresh(resume)

    dto = ResumeDetail.model_validate(resume)
    dto.candidate_name = cand.full_name
    text = resume.extracted_text or ""
    dto.candidate_email = cand.email or extract_email(text)
    dto.candidate_phone = cand.phone or extract_phone(text)
    dto.candidate_address = cand.address or extract_address(text)
    dto.candidate_linkedin = cand.linkedin or extract_linkedin(text)
    dto.professional_summary = build_professional_summary(text)
    dto.warnings = validate_contact(dto.candidate_email, dto.candidate_phone)

    AuditService(db).log(
        action="resumes.structured.update",
        resource_type="resume",
        resource_id=str(resume_id),
        ip=request.client.host if request.client else None,
        metadata={
            "approve_review": payload.approve_review,
            "old_primary_role": _extract_role_classification(old_structured)[0],
            "new_primary_role": _extract_role_classification(payload.structured_json or {})[0],
            "learning_total_feedback": ((learning_profile or {}).get("stats") or {}).get("total_feedback"),
        },
    )
    return dto


@router.patch("/{resume_id}/file", response_model=ResumeDetail)
def update_resume_file(
    resume_id: int,
    payload: ResumeFileUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    stmt = select(Resume, Candidate).join(Candidate, Candidate.id == Resume.candidate_id).where(Resume.id == resume_id)
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail="Currículo não encontrado")
    resume, cand = row
    source_path = Path(resume.file_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo físico não encontrado para atualização")

    settings = get_settings()
    recv_root = settings.recv_dir_path()
    dep_repo = DepartmentRepository(db)

    old_snapshot = {
        "file_path": resume.file_path,
        "filename": resume.original_filename,
        "department": resume.department,
        "filename_cargo": resume.filename_cargo,
        "candidate_name": cand.full_name,
    }

    new_department = (payload.new_department or resume.department or "").strip() or None
    new_cargo = (payload.new_cargo or resume.filename_cargo or "").strip() or resume.filename_cargo
    new_candidate_name = (payload.new_candidate_name or cand.full_name or "").strip() or cand.full_name
    if new_candidate_name and new_candidate_name != cand.full_name:
        cand.full_name = new_candidate_name
        db.add(cand)

    target_dir = source_path.parent
    if new_department:
        target_dir = recv_root / new_department
        target_dir.mkdir(parents=True, exist_ok=True)

    current_ext = source_path.suffix or ".pdf"
    if payload.new_filename:
        requested_name = payload.new_filename.strip()
        safe_name = requested_name if requested_name.endswith(current_ext) else f"{requested_name}{current_ext}"
    elif payload.apply_filename_pattern:
        safe_name = build_resume_filename(
            cargo=new_cargo,
            cnh=resume.filename_cnh,
            nome=new_candidate_name or cand.full_name,
            data_str=resume.filename_date,
            ext=current_ext,
        )
    else:
        safe_name = source_path.name

    target_path = target_dir / safe_name
    if target_path.resolve() != source_path.resolve():
        if target_path.exists():
            raise HTTPException(status_code=409, detail=f"Já existe um arquivo com este nome: {target_path.name}")
        source_path.replace(target_path)

    dep_row = None
    if new_department:
        dep_row = dep_repo.upsert(name=new_department, path=str(target_dir))

    resume.file_path = str(target_path)
    resume.original_filename = target_path.name
    resume.department = new_department
    resume.department_id = dep_row.id if dep_row else resume.department_id
    resume.filename_cargo = new_cargo
    resume.last_synced_at = datetime.utcnow()
    resume.processing_status = "synced"
    db.add(resume)

    new_snapshot = {
        "file_path": resume.file_path,
        "filename": resume.original_filename,
        "department": resume.department,
        "filename_cargo": resume.filename_cargo,
        "candidate_name": cand.full_name,
    }
    db.add(
        ResumeChangeHistory(
            resume_id=resume.id,
            action="file_update",
            old_value_json=json.dumps(old_snapshot, ensure_ascii=False),
            new_value_json=json.dumps(new_snapshot, ensure_ascii=False),
            reason=payload.reason,
            actor="api",
        )
    )
    db.commit()
    db.refresh(resume)

    dto = ResumeDetail.model_validate(resume)
    dto.candidate_name = cand.full_name
    text = resume.extracted_text or ""
    dto.candidate_email = cand.email or extract_email(text)
    dto.candidate_phone = cand.phone or extract_phone(text)
    dto.candidate_address = cand.address or extract_address(text)
    dto.candidate_linkedin = cand.linkedin or extract_linkedin(text)
    dto.professional_summary = build_professional_summary(text)
    dto.warnings = validate_contact(dto.candidate_email, dto.candidate_phone)

    AuditService(db).log(
        action="resumes.file_update",
        resource_type="resume",
        resource_id=str(resume_id),
        ip=request.client.host if request.client else None,
        metadata={"old": old_snapshot, "new": new_snapshot},
    )
    return dto


@router.get("/{resume_id}/history", response_model=list[ResumeHistoryOut])
def list_resume_history(
    resume_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ResumeChangeHistory)
        .filter(ResumeChangeHistory.resume_id == resume_id)
        .order_by(ResumeChangeHistory.created_at.desc())
        .all()
    )
    AuditService(db).log(
        action="resumes.history",
        resource_type="resume",
        resource_id=str(resume_id),
        ip=request.client.host if request.client else None,
        metadata={"items": len(rows)},
    )
    return [ResumeHistoryOut.model_validate(r) for r in rows]


def _extract_role_classification(structured_json: dict) -> tuple[str | None, list[str], float | None]:
    if not isinstance(structured_json, dict):
        return None, [], None
    fields = structured_json.get("fields")
    if not isinstance(fields, dict):
        return None, [], None
    role = fields.get("classificacao_cargo")
    if not isinstance(role, dict):
        return None, [], None
    primary = role.get("primary_role")
    secondary = role.get("secondary_roles")
    confidence = role.get("confidence")
    parsed_secondary = [str(x) for x in secondary] if isinstance(secondary, list) else []
    parsed_conf = float(confidence) if isinstance(confidence, (int, float)) else None
    return (str(primary) if primary else None, parsed_secondary[:5], parsed_conf)


def _sync_role_classification_to_applications(*, db: Session, candidate_id: int, structured_json: dict) -> None:
    primary, secondary, confidence = _extract_role_classification(structured_json)
    apps = db.query(Application).filter(Application.candidate_id == candidate_id).all()
    changed = False
    for app in apps:
        app.primary_role = primary
        app.secondary_roles_json = json.dumps(secondary, ensure_ascii=False)
        app.role_confidence = confidence
        db.add(app)
        changed = True
    if changed:
        db.commit()


@router.get("/{resume_id}/download")
def download_resume(resume_id: int, request: Request, db: Session = Depends(get_db)):
    resume = db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Currículo não encontrado")

    file_path = Path(resume.file_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no armazenamento")

    AuditService(db).log(
        action="resumes.download",
        resource_type="resume",
        resource_id=str(resume_id),
        ip=request.client.host if request.client else None,
        metadata={"path": str(file_path)},
    )
    return FileResponse(path=str(file_path), filename=file_path.name)


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: int,
    request: Request,
    delete_file: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    resume = db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Currículo não encontrado")

    file_path = Path(resume.file_path)
    snapshot = {
        "resume_id": resume.id,
        "candidate_id": resume.candidate_id,
        "file_path": resume.file_path,
        "filename": resume.original_filename,
        "delete_file": delete_file,
    }

    if delete_file and file_path.exists():
        try:
            file_path.unlink()
        except PermissionError:
            raise HTTPException(status_code=403, detail="Sem permissão para excluir o arquivo físico")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Falha ao excluir arquivo físico: {exc}")

    # Limpa vínculos derivados para evitar FK/órfãos.
    db.query(ResumeFile).filter(ResumeFile.resume_id == resume.id).delete(synchronize_session=False)
    db.query(ResumeChangeHistory).filter(ResumeChangeHistory.resume_id == resume.id).delete(synchronize_session=False)
    db.delete(resume)
    db.commit()

    AuditService(db).log(
        action="resumes.delete",
        resource_type="resume",
        resource_id=str(resume_id),
        ip=request.client.host if request.client else None,
        metadata=snapshot,
    )
    return {"status": "ok", "deleted_resume_id": resume_id, "file_deleted": delete_file}


@router.post("/actions/reclassify_young_apprentice")
def reclassify_false_young_apprentice(
    request: Request,
    dry_run: bool = Query(default=False),
    relink_applications: bool = Query(default=True),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    resumes = (
        db.execute(select(Resume).order_by(Resume.received_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    scanned = 0
    flagged = 0
    updated_resumes = 0
    moved_apps = 0
    staged_out_apps = 0
    samples: list[dict] = []

    for resume in resumes:
        scanned += 1
        text = resume.extracted_text or ""
        filename_role = resume.filename_cargo
        primary_role, primary_conf = _extract_primary_role(resume.structured_json)
        young_label = _is_young_apprentice_label(filename_role) or _is_young_apprentice_label(primary_role)
        if not young_label:
            continue
        senior = _has_senior_signals(text)
        apprentice = _has_apprentice_signals(text)
        false_positive = senior or not apprentice
        if not false_positive:
            continue

        flagged += 1
        target_role = None
        if primary_role and not _is_young_apprentice_label(primary_role):
            # Ignora classificações fracas (ex.: "TI" por ruído textual).
            if (primary_conf or 0.0) >= 0.45 and len(_norm(primary_role)) > 2:
                target_role = primary_role
        if not target_role:
            target_role = _infer_role_from_text(text)
        cand_apps = db.execute(select(Application).where(Application.candidate_id == resume.candidate_id)).scalars().all()
        young_apps = []
        for app in cand_apps:
            job = db.get(Job, app.job_id)
            if job and _is_young_apprentice_label(job.title):
                young_apps.append((app, job))
        target_job = _find_matching_job(db, target_role)
        target_app_exists = bool(
            target_job and db.execute(
                select(Application).where(
                    Application.candidate_id == resume.candidate_id,
                    Application.job_id == target_job.id,
                )
            ).scalars().first()
        )

        if not dry_run:
            if target_role and (resume.filename_cargo or "").strip() != target_role.strip():
                resume.filename_cargo = target_role
                db.add(resume)
                updated_resumes += 1

            if relink_applications and target_job:
                for app, _job in young_apps:
                    if target_app_exists:
                        if app.stage != ApplicationStage.banco_talentos.value:
                            from_stage = app.stage
                            app.stage = ApplicationStage.banco_talentos.value
                            db.add(app)
                            db.add(
                                StageHistory(
                                    application_id=app.id,
                                    from_stage=from_stage,
                                    to_stage=ApplicationStage.banco_talentos.value,
                                    note="Reclassificação automática: falso jovem aprendiz",
                                )
                            )
                            staged_out_apps += 1
                    else:
                        app.job_id = target_job.id
                        from_stage = app.stage
                        app.stage = ApplicationStage.recebido.value
                        db.add(app)
                        db.add(
                            StageHistory(
                                application_id=app.id,
                                from_stage=from_stage,
                                to_stage=ApplicationStage.recebido.value,
                                note=f"Reclassificação automática para vaga: {target_job.title}",
                            )
                        )
                        moved_apps += 1
                        target_app_exists = True

        if len(samples) < 30:
            samples.append(
                {
                    "resume_id": resume.id,
                    "candidate_id": resume.candidate_id,
                    "filename_cargo": filename_role,
                    "primary_role": primary_role,
                    "target_job": target_job.title if target_job else None,
                    "young_apps": len(young_apps),
                }
            )

    if not dry_run:
        db.commit()

    result = {
        "dry_run": dry_run,
        "scanned": scanned,
        "flagged_false_young_apprentice": flagged,
        "updated_resumes": updated_resumes,
        "moved_applications_to_target_job": moved_apps,
        "staged_out_young_applications": staged_out_apps,
        "samples": samples,
    }
    AuditService(db).log(
        action="resumes.reclassify_young_apprentice",
        ip=request.client.host if request.client else None,
        metadata=result,
    )
    return result
