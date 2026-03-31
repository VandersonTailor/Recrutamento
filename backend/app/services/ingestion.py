import re
import ast
import unicodedata
from datetime import datetime
from pathlib import Path
from functools import lru_cache

from sqlalchemy.orm import Session
import json

from app.core.config import get_settings
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.common import ApplicationStage, SourceChannel
from app.models.job import Job
from app.models.resume import Resume
from app.models.stage_history import StageHistory
from app.repositories.applications import ApplicationRepository
from app.repositories.candidates import CandidateRepository
from app.repositories.jobs import JobRepository
from app.repositories.resumes import ResumeRepository
from app.repositories.departments import DepartmentRepository
from app.services.ai import analyze_resume
from app.services.text_extraction import extract_text, sha256_file
from app.services.match import compute_match
from app.services.scoring import read_scoring_profile
from app.services.resume_structuring import structure_resume_text
from app.services.resume_file_naming import parse_resume_filename
from app.models.resume_file import ResumeFile
import hashlib
import mimetypes
import time
from app.models.processing_log import ProcessingLog


class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.candidates = CandidateRepository(db)
        self.resumes = ResumeRepository(db)
        self.jobs = JobRepository(db)
        self.applications = ApplicationRepository(db)
        self.departments = DepartmentRepository(db)

    def scan_recv_dir(self, *, job_id: int | None, force_reanalyze: bool) -> dict:
        recv_dir = self.settings.recv_dir_path()
        if not recv_dir.exists() or not recv_dir.is_dir():
            raise FileNotFoundError(f"recv_dir não encontrado ou inacessível: {recv_dir}")

        counters = {
            "scanned_files": 0,
            "created_candidates": 0,
            "created_resumes": 0,
            "created_applications": 0,
            "updated_applications": 0,
        }

        job_scan_context = None
        if job_id:
            job = self.jobs.get(job_id)
            if not job:
                raise FileNotFoundError(f"Vaga não encontrada para job_id={job_id}")
            job_scan_context = self._build_job_scan_context(job=job, recv_dir=recv_dir)

        for path in self._iter_resume_files(recv_dir, job_scan_context=job_scan_context):
            counters["scanned_files"] += 1
            self._ingest_file(path=path, job_id=job_id, force_reanalyze=force_reanalyze, counters=counters)

        return counters

    def ingest_report_from_bot(self, payload: dict) -> dict:
        file_path = payload.get("file_path") or ""
        if not file_path:
            return {"status": "ignored", "reason": "missing_file_path"}
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return {"status": "ignored", "reason": "file_not_found"}

        counters = {
            "scanned_files": 1,
            "created_candidates": 0,
            "created_resumes": 0,
            "created_applications": 0,
            "updated_applications": 0,
        }
        self._ingest_file(path=path, job_id=None, force_reanalyze=False, counters=counters, bot_payload=payload)
        return {"status": "ok", **counters}

    def reconcile_candidates_from_resumes(self) -> dict:
        updated_resumes = 0
        created_candidates = 0
        updated_applications = 0
        updated_departments = 0

        resumes = list(self.db.query(Resume).all())
        for resume in resumes:
            parsed = self._parse_from_filename(Path(resume.file_path).name)
            structured_name = None
            try:
                if resume.structured_json:
                    st = json.loads(resume.structured_json)
                    if isinstance(st, dict):
                        structured_name = ((st.get("fields", {}) or {}).get("nome"))
            except Exception:
                structured_name = None
            nome = (
                _clean_candidate_name(structured_name)
                or _clean_candidate_name(parsed.get("nome"))
                or _clean_candidate_name(_guess_name_from_text(resume.extracted_text or ""))
            )
            if not nome:
                continue

            dep = self._infer_department(Path(resume.file_path))
            if dep and resume.department != dep:
                resume.department = dep
                self.db.add(resume)
                self.db.commit()
                updated_departments += 1

            candidate = self.candidates.find(email=None, phone=None, full_name=nome)
            if not candidate:
                candidate = self.candidates.create(Candidate(full_name=nome, email=None, phone=None))
                created_candidates += 1

            if resume.candidate_id != candidate.id:
                old_candidate_id = resume.candidate_id
                resume.candidate_id = candidate.id
                self.db.add(resume)
                self.db.commit()
                updated_resumes += 1

                cargo = (parsed.get("cargo") or "").strip()
                if cargo:
                    job = None
                    for j in self.jobs.list(active_only=False):
                        if j.title.strip().lower() == cargo.lower():
                            job = j
                            break
                    if job:
                        app = self.applications.get_by_candidate_job(candidate_id=old_candidate_id, job_id=job.id)
                        if app:
                            app.candidate_id = candidate.id
                            self.applications.update(app)
                            updated_applications += 1

        return {
            "status": "ok",
            "updated_resumes": updated_resumes,
            "created_candidates": created_candidates,
            "updated_applications": updated_applications,
            "updated_departments": updated_departments,
        }

    def _iter_resume_files(self, recv_dir: Path, job_scan_context: dict | None = None):
        allowed = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}
        for path in recv_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix.lower() not in allowed:
                continue
            if job_scan_context and not self._matches_job_scan(path=path, ctx=job_scan_context):
                continue
            yield path

    def _build_job_scan_context(self, *, job: Job, recv_dir: Path) -> dict:
        title_norm = _norm_text(job.title)
        setor, source = _infer_setor_from_title(job.title)
        target_folders = _resolve_target_folders(recv_dir=recv_dir, setor=setor)
        return {
            "job_id": job.id,
            "job_title": job.title,
            "job_title_norm": title_norm,
            "setor": setor,
            "setor_source": source,
            "target_folders": target_folders,
        }

    def _matches_job_scan(self, *, path: Path, ctx: dict) -> bool:
        target_folders: list[Path] = ctx.get("target_folders") or []
        if target_folders:
            in_allowed_folder = False
            for folder in target_folders:
                try:
                    path.resolve().relative_to(folder.resolve())
                    in_allowed_folder = True
                    break
                except Exception:
                    continue
            if not in_allowed_folder:
                return False

        parsed = self._parse_from_filename(path.name)
        cargo_from_filename = _norm_text(parsed.get("cargo") or "")
        title_norm = ctx.get("job_title_norm") or ""
        setor = ctx.get("setor") or ""

        # Regra do bot para Motorista: ao abrir vaga motorista, usa todos da pasta motorista.
        if _norm_text(setor) == "motorista":
            return True

        stem_norm = _norm_text(path.stem)
        if cargo_from_filename:
            return _is_cargo_match(job_title_norm=title_norm, candidate_cargo_norm=cargo_from_filename)
        return _is_cargo_match(job_title_norm=title_norm, candidate_cargo_norm=stem_norm)

    def _ingest_file(
        self,
        *,
        path: Path,
        job_id: int | None,
        force_reanalyze: bool,
        counters: dict,
        bot_payload: dict | None = None,
    ) -> None:
        t0 = time.time()
        status = "success"
        msg = None
        dep_name_for_log = None
        try:
            file_hash = sha256_file(path)
            existing_by_hash = self.resumes.get_by_hash(file_hash)
            if existing_by_hash:
                status = "skipped"
                msg = "duplicate_by_hash"
                # Mesmo com arquivo já ingerido, uma vaga nova precisa gerar candidatura
                # para o candidato correspondente.
                if job_id:
                    self._maybe_reanalyze_for_job(file_hash=file_hash, job_id=job_id, counters=counters)
                return

            parsed = self._parse_from_filename(path.name)
            existing_by_path = self.resumes.get_by_path(str(path))
            extracted = extract_text(path)
            structured = structure_resume_text(text=extracted or "", fallback_name=parsed.get("nome"))

            email, phone = _extract_contact(extracted)
            full_name = (
                (bot_payload or {}).get("nome")
                or parsed.get("nome")
                or ((structured.get("fields", {}) or {}).get("nome") if isinstance(structured, dict) else None)
                or _guess_name_from_text(extracted)
                or "SEMNOME"
            )
            full_name = _clean_candidate_name(full_name) or _clean_candidate_name(_guess_name_from_text(extracted)) or "SEMNOME"

            existing = self.candidates.find(email=email, phone=phone, full_name=full_name)
            if existing:
                candidate = existing
            else:
                candidate = self.candidates.create(Candidate(full_name=full_name, email=email, phone=phone))
                counters["created_candidates"] += 1

            source = _map_source_channel((bot_payload or {}).get("origem"))
            received_at = _parse_received_at(bot_payload)

            dep_name = self._infer_department(path)
            dep_row = None
            if dep_name:
                dep_row = self.departments.upsert(name=dep_name, path=str(path.parent))
            dep_name_for_log = dep_name

            if existing_by_path:
                resume = existing_by_path
                resume.candidate_id = candidate.id
                resume.source_channel = source
                resume.received_at = received_at
                resume.department = dep_name
                resume.department_id = dep_row.id if dep_row else None
                resume.original_filename = path.name
                resume.file_hash = file_hash
                resume.extracted_text = extracted if extracted else None
                resume.parsed_json = None
                resume.structured_json = json.dumps(structured, ensure_ascii=False)
                resume.extraction_confidence = structured.get("quality", {}).get("confidence")
                resume.requires_manual_review = bool(structured.get("quality", {}).get("requires_manual_review"))
                resume.review_reason = structured.get("quality", {}).get("review_reason")
                resume.filename_cargo = parsed.get("cargo")
                resume.filename_cnh = parsed.get("cnh")
                resume.filename_date = parsed.get("data")
                resume.processing_status = "reprocessed"
                resume.last_synced_at = datetime.utcnow()
                resume = self.resumes.update(resume)
            else:
                resume = self.resumes.create(
                    Resume(
                        candidate_id=candidate.id,
                        source_channel=source,
                        received_at=received_at,
                        department=dep_name,
                        department_id=(dep_row.id if dep_row else None),
                        original_filename=path.name,
                        file_path=str(path),
                        file_hash=file_hash,
                        filename_cargo=parsed.get("cargo"),
                        filename_cnh=parsed.get("cnh"),
                        filename_date=parsed.get("data"),
                        imported_at=datetime.utcnow(),
                        last_synced_at=datetime.utcnow(),
                        processing_status="processed",
                        extracted_text=extracted if extracted else None,
                        parsed_json=None,
                        structured_json=json.dumps(structured, ensure_ascii=False),
                        extraction_confidence=structured.get("quality", {}).get("confidence"),
                        requires_manual_review=bool(structured.get("quality", {}).get("requires_manual_review")),
                        review_reason=structured.get("quality", {}).get("review_reason"),
                    )
                )
                counters["created_resumes"] += 1

            if self.settings.store_files_in_db:
                try:
                    size = path.stat().st_size
                    if size <= self.settings.max_file_bytes_in_db and path.suffix.lower() in {".pdf", ".doc", ".docx"}:
                        with path.open("rb") as f:
                            content = f.read()
                        md5 = hashlib.md5(content).hexdigest()
                        exists = self.db.query(ResumeFile).filter(ResumeFile.md5 == md5).first()
                        if not exists:
                            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                            rf = ResumeFile(resume_id=resume.id, md5=md5, mime_type=mime, size_bytes=size, content=content)
                            self.db.add(rf)
                            self.db.commit()
                except Exception:
                    pass

            job = None
            if job_id:
                job = self.jobs.get(job_id)
            if not job:
                cargo = (bot_payload or {}).get("cargo") or parsed.get("cargo")
                # Guardrail: evita classificar como Jovem Aprendiz quando o currículo
                # traz sinais fortes de profissional experiente.
                if _is_jovem_aprendiz_label(cargo) and (
                    _has_senior_experience_profile(extracted or "")
                    or not _has_young_apprentice_profile(extracted or "")
                ):
                    cargo = None
                if not cargo:
                    cargo = _structured_primary_role(structured)
                if cargo:
                    job = self._get_or_create_job_from_cargo(cargo=str(cargo), department=self._infer_department(path))

            if job:
                existing_app = self.applications.get_by_candidate_job(candidate_id=candidate.id, job_id=job.id)
                if existing_app:
                    if force_reanalyze:
                        self._run_analysis_and_update(application=existing_app, resume_text=extracted, job=job)
                        counters["updated_applications"] += 1
                    return

                if not self._candidate_available_for_new_job(candidate_id=candidate.id, current_job_id=job.id):
                    return

                app = self.applications.create(
                    Application(
                        candidate_id=candidate.id,
                        job_id=job.id,
                        stage=ApplicationStage.recebido.value,
                    )
                )
                self.db.add(StageHistory(application_id=app.id, from_stage=None, to_stage=app.stage, note="Recebido"))
                self.db.commit()
                counters["created_applications"] += 1

                self._run_analysis_and_update(application=app, resume_text=extracted, job=job)
                counters["updated_applications"] += 1
        except Exception as e:
            status = "error"
            msg = str(e)
        finally:
            try:
                duration_ms = int((time.time() - t0) * 1000)
                pl = ProcessingLog(
                    file_path=str(path),
                    department=dep_name_for_log,
                    status=status,
                    message=msg,
                    duration_ms=duration_ms,
                )
                self.db.add(pl)
                self.db.commit()
            except Exception:
                pass

    def _infer_department(self, path: Path) -> str | None:
        try:
            recv_dir = self.settings.recv_dir_path().resolve()
            rel = path.resolve().relative_to(recv_dir)
            if len(rel.parts) >= 2:
                return rel.parts[0]
        except Exception:
            return None
        return None

    def _get_or_create_job_from_cargo(self, *, cargo: str, department: str | None) -> Job:
        cargo_norm = cargo.strip()
        for j in self.jobs.list(active_only=False):
            if j.title.strip().lower() == cargo_norm.lower():
                return j
        return self.jobs.create(Job(title=cargo_norm, department=department))

    def _maybe_reanalyze_for_job(self, *, file_hash: str, job_id: int, counters: dict) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        stmt = self.db.query(Resume).filter(Resume.file_hash == file_hash).limit(1)
        resume = stmt.first()
        if not resume:
            return
        app = self.applications.get_by_candidate_job(candidate_id=resume.candidate_id, job_id=job.id)
        if not app:
            if not self._candidate_available_for_new_job(candidate_id=resume.candidate_id, current_job_id=job.id):
                return
            app = self.applications.create(
                Application(candidate_id=resume.candidate_id, job_id=job.id, stage=ApplicationStage.recebido.value)
            )
            self.db.add(StageHistory(application_id=app.id, from_stage=None, to_stage=app.stage, note="Recebido"))
            self.db.commit()
            counters["created_applications"] += 1
        self._run_analysis_and_update(application=app, resume_text=resume.extracted_text or "", job=job)
        counters["updated_applications"] += 1

    def _run_analysis_and_update(self, *, application: Application, resume_text: str, job: Job) -> None:
        analysis = analyze_resume(
            resume_text=resume_text or "",
            job_title=job.title,
            job_description=job.description,
            job_requirements=job.requirements,
        )
        application.score = analysis.score_aderencia
        application.score_justification = analysis.justificativa_score
        application.experience_years = analysis.tempo_experiencia_anos
        application.seniority = analysis.senioridade
        application.strengths = "\n".join(analysis.pontos_fortes) if analysis.pontos_fortes else None
        application.concerns = "\n".join(analysis.pontos_atencao) if analysis.pontos_atencao else None
        application.analysis_json = None if not analysis.raw_json else json.dumps(analysis.raw_json, ensure_ascii=False)
        try:
            st = self._latest_structured_for_candidate(candidate_id=application.candidate_id)
            role = ((st.get("fields", {}) or {}).get("classificacao_cargo") or {}) if isinstance(st, dict) else {}
            application.primary_role = role.get("primary_role") if isinstance(role, dict) else None
            if isinstance(role, dict):
                secondary = role.get("secondary_roles") or []
                application.secondary_roles_json = json.dumps(secondary if isinstance(secondary, list) else [], ensure_ascii=False)
                rc = role.get("confidence")
                application.role_confidence = float(rc) if isinstance(rc, (int, float)) else None
        except Exception:
            pass
        # Matching inteligente (MVP): calcula percentual total com os pesos definidos
        try:
            structured = self._latest_structured_for_candidate(candidate_id=application.candidate_id)
            breakdown = compute_match(
                application,
                job,
                resume_text=resume_text or "",
                scoring_profile=read_scoring_profile(job),
                resume_structured=structured,
            )
            application.score = breakdown.total
            if application.score_justification:
                application.score_justification += f"\nMatch: cargo={breakdown.cargo:.0f}%, formação={breakdown.formacao:.0f}%, cursos={breakdown.cursos:.0f}%, experiência={breakdown.experiencia:.0f}%, bônus localização={breakdown.localizacao_bonus:.0f}pts"
            else:
                application.score_justification = f"Match: cargo={breakdown.cargo:.0f}%, formação={breakdown.formacao:.0f}%, cursos={breakdown.cursos:.0f}%, experiência={breakdown.experiencia:.0f}%, bônus localização={breakdown.localizacao_bonus:.0f}pts"
            if breakdown.highlights:
                hl = "; ".join(breakdown.highlights)
                application.strengths = (application.strengths + "\n" if application.strengths else "") + f"Destaques: {hl}"
        except Exception:
            pass
        self.applications.update(application)

    def _latest_structured_for_candidate(self, *, candidate_id: int) -> dict:
        resume = (
            self.db.query(Resume)
            .filter(Resume.candidate_id == candidate_id, Resume.structured_json.is_not(None))
            .order_by(Resume.received_at.desc())
            .limit(1)
            .first()
        )
        if not resume or not resume.structured_json:
            return {}
        try:
            return json.loads(resume.structured_json)
        except Exception:
            return {}

    def _candidate_available_for_new_job(self, *, candidate_id: int, current_job_id: int) -> bool:
        stmt = (
            self.db.query(Application)
            .filter(
                Application.candidate_id == candidate_id,
                Application.job_id != current_job_id,
                Application.stage != ApplicationStage.banco_talentos.value,
            )
            .limit(1)
        )
        locked = stmt.first()
        return locked is None

    def _parse_from_filename(self, filename: str) -> dict:
        return parse_resume_filename(filename)


def _extract_contact(text: str) -> tuple[str | None, str | None]:
    email = None
    m_email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text or "", flags=re.IGNORECASE)
    if m_email:
        email = m_email.group(0).strip()

    phone = None
    m_phone = re.search(r"(\+\d{1,3}\s*)?(\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}", text or "")
    if m_phone:
        phone = re.sub(r"\D", "", m_phone.group(0))
        if len(phone) > 13:
            phone = phone[-13:]
    return email, phone


def _guess_name_from_text(text: str) -> str | None:
    if not text:
        return None
    explicit = re.search(r"\bnome\s*[:\-]\s*([A-Za-zÀ-ÿ' ]{5,120})", text, flags=re.IGNORECASE)
    if explicit:
        return _clean_candidate_name(explicit.group(1))

    first_nonempty = None
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 3:
            first_nonempty = s
            break
    if not first_nonempty:
        return None
    if len(first_nonempty) > 80:
        return None
    return _clean_candidate_name(first_nonempty)


def _map_source_channel(origem: str | None) -> str:
    o = (origem or "").strip().lower()
    if "whats" in o or o == "wpp":
        return SourceChannel.whatsapp.value
    if "mail" in o or "email" in o:
        return SourceChannel.email.value
    return SourceChannel.unknown.value


def _parse_received_at(payload: dict | None) -> datetime:
    if not payload:
        return datetime.utcnow()
    v = payload.get("received_at")
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return datetime.utcnow()
    return datetime.utcnow()


def _clean_candidate_name(value: str | None) -> str | None:
    if not value:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip(" .,-")
    if len(s) < 4:
        return None
    n = _norm_text(s)
    blocked = {"semnome", "sem nome", "desconhecido", "nao informado", "não informado", "candidato"}
    if n in blocked:
        return None
    noisy_fragments = (
        "experiencia",
        "atendente",
        "operador",
        "padaria",
        "empacotadora",
        "titulo de eleitor",
        "objetivo",
        "perfil profissional",
        "primeiro emprego",
        "responsavel",
        "determinado",
        "aprendo rapido",
        "atencioso",
    )
    if any(frag in n for frag in noisy_fragments):
        return None
    if len(s.split()) < 2:
        return None
    return s


def _norm_text(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    raw = re.sub(r"[^a-z0-9\s_/-]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _tokenize(value: str) -> list[str]:
    stop = {"de", "da", "do", "dos", "das", "e", "i", "ii", "iii", "iv", "v"}
    tokens = [t for t in _norm_text(value).replace("-", " ").replace("/", " ").split() if t and t not in stop]
    return tokens


def _is_jovem_aprendiz_label(value: str | None) -> bool:
    n = _norm_text(value or "")
    return "jovem aprendiz" in n or "menor aprendiz" in n or n == "aprendiz" or n == "jovem_aprendiz"


def _has_senior_experience_profile(text: str) -> bool:
    n = _norm_text(text or "")
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
    strong_role_keywords = (
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
    has_strong_role = any(k in n for k in strong_role_keywords)
    if has_strong_role:
        return True

    years = re.findall(r"\b(?:19|20)\d{2}\b", text or "")
    company_signals = len(re.findall(r"\bempresa\b", n))
    # Histórico de estágio não deve, sozinho, caracterizar perfil sênior.
    if has_internship_profile and len(years) < 6 and company_signals < 3:
        return False
    if len(years) >= 4:
        return True
    if company_signals >= 2:
        return True
    return False


def _has_young_apprentice_profile(text: str) -> bool:
    n = _norm_text(text or "")
    if not n:
        return False
    signals = (
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
    return any(s in n for s in signals)


def _structured_primary_role(structured: dict | None) -> str | None:
    if not isinstance(structured, dict):
        return None
    fields = structured.get("fields")
    if not isinstance(fields, dict):
        return None
    role = fields.get("classificacao_cargo")
    if not isinstance(role, dict):
        return None
    primary = role.get("primary_role")
    if isinstance(primary, str) and primary.strip():
        return primary.strip()
    return None


def _is_cargo_match(*, job_title_norm: str, candidate_cargo_norm: str) -> bool:
    if not job_title_norm or not candidate_cargo_norm:
        return False

    if job_title_norm == candidate_cargo_norm:
        return True
    if job_title_norm in candidate_cargo_norm or candidate_cargo_norm in job_title_norm:
        return True

    job_tokens = set(_tokenize(job_title_norm))
    cargo_tokens = set(_tokenize(candidate_cargo_norm))
    if not job_tokens or not cargo_tokens:
        return False

    inter = job_tokens.intersection(cargo_tokens)
    if len(inter) >= 2:
        return True

    # Ex.: "aux servicos gerais" casa com "aux servicos gerais ii"
    if len(job_tokens) >= 2 and job_tokens.issubset(cargo_tokens):
        return True
    if len(cargo_tokens) >= 2 and cargo_tokens.issubset(job_tokens):
        return True

    return False


@lru_cache(maxsize=1)
def _bot_maps() -> tuple[dict[str, str], dict[str, str]]:
    """
    Extrai do bot.py os mapas SETORES (setor->pasta) e CARGOS (cargo->setor),
    para manter o backend alinhado com a mesma dinâmica do bot.
    """
    setores_map: dict[str, str] = {}
    cargos_map: dict[str, str] = {}

    bot_path = Path(__file__).resolve().parents[3] / "bot.py"
    if not bot_path.exists():
        return setores_map, cargos_map

    try:
        mod = ast.parse(bot_path.read_text(encoding="utf-8"))
    except Exception:
        return setores_map, cargos_map

    for node in mod.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        if tgt.id == "CARGOS" and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    cargos_map[_norm_text(k.value)] = v.value
        if tgt.id == "SETORES" and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                    continue
                folder = _extract_folder_literal(v)
                if folder:
                    setores_map[k.value] = folder

    return setores_map, cargos_map


def _extract_folder_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = _extract_folder_literal(node.right)
        if right:
            return right
    return None


def _infer_setor_from_title(title: str) -> tuple[str | None, str]:
    title_norm = _norm_text(title)
    if not title_norm:
        return None, "empty"

    setores_map, cargos_map = _bot_maps()
    if title_norm in cargos_map:
        return cargos_map[title_norm], "bot_exact"

    # Match parcial em cargos do bot (maior chave primeiro)
    best_key = None
    for key in sorted(cargos_map.keys(), key=len, reverse=True):
        if key and (key in title_norm or title_norm in key):
            best_key = key
            break
    if best_key:
        return cargos_map.get(best_key), "bot_partial"

    # Heurísticas de fallback
    if any(t in title_norm for t in ("motorista", "manobrista", "condutor")):
        return "Motorista", "heuristic"
    if any(t in title_norm for t in ("manutencao", "mecanic", "eletric", "borrache", "chapea", "lavador", "socorrista", "servicos gerais", "servicos geral", "aux servicos")):
        return "Manutencao", "heuristic"
    if any(t in title_norm for t in ("trafego", "fiscal", "operacao", "vistoriador", "escala")):
        return "Operacao", "heuristic"
    if any(t in title_norm for t in ("rh", "administr", "jurid", "financeir", "contabil", "dp", "departamento pessoal", "recepc")):
        return "Administrativo", "heuristic"

    # Se não achar, deixa sem setor para evitar varrer pasta errada.
    return None, "none"


def _resolve_target_folders(*, recv_dir: Path, setor: str | None) -> list[Path]:
    if not setor:
        return []

    setores_map, _ = _bot_maps()
    folder_name = setores_map.get(setor)
    if folder_name:
        p = recv_dir / folder_name
        if p.exists() and p.is_dir():
            return [p]

    # fallback por nome da pasta no recv_dir
    wanted = _norm_text(setor)
    direct_matches: list[Path] = []
    for child in recv_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        c_norm = _norm_text(child.name)
        if c_norm == wanted or wanted in c_norm or c_norm in wanted:
            direct_matches.append(child)

    return direct_matches


def infer_setor_from_job_title(title: str) -> str | None:
    setor, _ = _infer_setor_from_title(title)
    return setor
