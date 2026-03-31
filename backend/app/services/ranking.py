import json
import time
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.common import ApplicationStage
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.resume import Resume
from app.services.match import compute_match
from app.services.resume_view import build_professional_summary, extract_address, extract_email, extract_linkedin, extract_phone
from app.services.scoring import read_scoring_profile


_CACHE: dict[str, tuple[float, object]] = {}


class RankingService:
    def __init__(self, db: Session):
        self.db = db

    def rank_job(
        self,
        *,
        job_id: int,
        department: str | None,
        min_score: float | None,
        q: str | None,
        limit: int,
        use_cache: bool = True,
        ttl_seconds: int = 30,
    ) -> dict:
        cache_key = f"job:{job_id}|dep:{department or ''}|min:{min_score or ''}|q:{q or ''}|limit:{limit}"
        now = time.time()
        if use_cache:
            hit = _CACHE.get(cache_key)
            if hit and now - hit[0] <= ttl_seconds:
                return hit[1]  # type: ignore[return-value]

        job = self.db.get(Job, job_id)
        if not job:
            return {"job_id": job_id, "items": []}

        if department is None:
            department = job.department

        items = self._rank_from_applications(job=job, department=department, min_score=min_score, q=q, limit=limit)

        out = {
            "job_id": job.id,
            "job_title": job.title,
            "department": department,
            "count": len(items),
            "items": items,
        }

        if use_cache:
            _CACHE[cache_key] = (now, out)
        return out

    def _rank_from_applications(
        self,
        *,
        job: Job,
        department: str | None,
        min_score: float | None,
        q: str | None,
        limit: int,
    ) -> list[dict]:
        stmt = (
            select(Application, Candidate)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .where(
                Application.job_id == job.id,
                Application.stage == ApplicationStage.recebido.value,
            )
            .order_by(Application.score.desc().nullslast(), Application.updated_at.desc())
        )
        if min_score is not None:
            stmt = stmt.where(Application.score.is_not(None), Application.score >= min_score)
        if q:
            stmt = stmt.where(Candidate.full_name.ilike(f"%{q}%"))

        rows = self.db.execute(stmt).all()
        if not rows and department:
            return self._rank_from_resumes(job=job, department=department, min_score=min_score, q=q, limit=limit)

        out: list[dict] = []
        for app, cand in rows[: max(200, limit)]:
            resume = self._latest_resume_for_candidate(candidate_id=cand.id, department=department)
            item = self._build_item(job=job, cand=cand, app=app, resume=resume)
            if min_score is None or item["match_percent"] >= float(min_score):
                out.append(item)

        out.sort(key=self._rank_sort_key, reverse=True)
        ranked = out[:limit]
        self._annotate_rank_reasons(ranked)
        return ranked

    def _rank_from_resumes(
        self,
        *,
        job: Job,
        department: str,
        min_score: float | None,
        q: str | None,
        limit: int,
    ) -> list[dict]:
        stmt = (
            select(Resume, Candidate)
            .join(Candidate, Candidate.id == Resume.candidate_id)
            .where(Resume.department == department, Resume.missing_in_storage.is_(False))
            .order_by(Resume.received_at.desc())
            .limit(500)
        )
        if q:
            stmt = stmt.where(Candidate.full_name.ilike(f"%{q}%"))
        rows = self.db.execute(stmt).all()

        out: list[dict] = []
        for resume, cand in rows:
            if self._candidate_has_job_application(candidate_id=cand.id, job_id=job.id):
                continue
            if self._candidate_locked_for_search(candidate_id=cand.id, current_job_id=job.id):
                continue
            fake_app = Application(
                candidate_id=cand.id,
                job_id=job.id,
                stage="Recebido",
                score=None,
                score_justification=None,
                experience_years=None,
                seniority="Indefinido",
                strengths=None,
                concerns=None,
                analysis_json=resume.parsed_json,
            )
            item = self._build_item(job=job, cand=cand, app=fake_app, resume=resume)
            if min_score is None or item["match_percent"] >= float(min_score):
                out.append(item)

        out.sort(key=self._rank_sort_key, reverse=True)
        ranked = out[:limit]
        self._annotate_rank_reasons(ranked)
        return ranked

    def _candidate_has_job_application(self, *, candidate_id: int, job_id: int) -> bool:
        stmt = (
            select(Application.id)
            .where(Application.candidate_id == candidate_id, Application.job_id == job_id)
            .limit(1)
        )
        return self.db.execute(stmt).first() is not None

    def _candidate_locked_for_search(self, *, candidate_id: int, current_job_id: int) -> bool:
        stmt = (
            select(Application.id)
            .where(
                Application.candidate_id == candidate_id,
                Application.job_id != current_job_id,
                Application.stage != ApplicationStage.banco_talentos.value,
            )
            .limit(1)
        )
        return self.db.execute(stmt).first() is not None

    def _latest_resume_for_candidate(self, *, candidate_id: int, department: str | None) -> Resume | None:
        stmt = (
            select(Resume)
            .where(Resume.candidate_id == candidate_id, Resume.missing_in_storage.is_(False))
            .order_by(Resume.received_at.desc())
            .limit(1)
        )
        if department:
            stmt = stmt.where(Resume.department == department)
        return self.db.execute(stmt).scalars().first()

    def _build_item(self, *, job: Job, cand: Candidate, app: Application, resume: Resume | None) -> dict:
        text = (resume.extracted_text if resume and resume.extracted_text else "") or ""
        scoring_profile = read_scoring_profile(job)
        primary_role, secondary_roles, role_confidence, role_needs_review = self._roles_from_resume(resume)
        structured = self._safe_structured(resume)

        email = cand.email or extract_email(text)
        phone = cand.phone or extract_phone(text)
        address = cand.address or extract_address(text)
        linkedin = cand.linkedin or extract_linkedin(text)

        breakdown = compute_match(
            app,
            job,
            resume_text=text,
            candidate_address=address,
            scoring_profile=scoring_profile,
            resume_structured=structured,
        )
        summary = build_professional_summary(text)

        strengths = []
        if app.strengths:
            strengths.extend([x.strip() for x in app.strengths.splitlines() if x.strip()])
        strengths.extend(breakdown.highlights)
        strengths = strengths[:8]

        return {
            "candidate_id": cand.id,
            "candidate_name": cand.full_name,
            "email": email,
            "phone": phone,
            "linkedin": linkedin,
            "address": address,
            "match_percent": float(round(breakdown.total, 2)),
            "match_breakdown": asdict(breakdown),
            "justification": app.score_justification,
            "professional_summary": summary,
            "strengths": strengths,
            "stage": app.stage,
            "application_id": getattr(app, "id", None),
            "resume_id": getattr(resume, "id", None),
            "experience_years": app.experience_years,
            "updated_at": getattr(app, "updated_at", None),
            "scoring_profile": scoring_profile,
            "primary_role": primary_role,
            "secondary_roles": secondary_roles,
            "role_confidence": role_confidence,
            "role_needs_review": role_needs_review,
        }

    def _rank_sort_key(self, item: dict) -> tuple:
        # Desempate empresarial determinístico:
        # 1) score total
        # 2) confiança de classificação de cargo
        # 3) anos de experiência
        # 4) data de atualização da candidatura
        # 5) id do candidato (estabilidade)
        updated = item.get("updated_at")
        updated_ts = 0.0
        try:
            if updated is not None:
                updated_ts = updated.timestamp() if hasattr(updated, "timestamp") else 0.0
        except Exception:
            updated_ts = 0.0
        return (
            float(item.get("match_percent") or 0.0),
            float(item.get("role_confidence") or 0.0),
            float(item.get("experience_years") or 0.0),
            updated_ts,
            float(item.get("candidate_id") or 0.0),
        )

    def _annotate_rank_reasons(self, items: list[dict]) -> None:
        prev: dict | None = None
        for idx, it in enumerate(items, start=1):
            it["rank_position"] = idx
            if prev is None:
                it["rank_reason"] = "Top score geral"
                prev = it
                continue

            cur_score = float(it.get("match_percent") or 0.0)
            prev_score = float(prev.get("match_percent") or 0.0)
            if cur_score < prev_score:
                it["rank_reason"] = "Pontuação total inferior ao candidato acima"
            else:
                cur_role = float(it.get("role_confidence") or 0.0)
                prev_role = float(prev.get("role_confidence") or 0.0)
                cur_exp = float(it.get("experience_years") or 0.0)
                prev_exp = float(prev.get("experience_years") or 0.0)
                if cur_role < prev_role:
                    it["rank_reason"] = "Empate de score resolvido por menor confiança de cargo"
                elif cur_exp < prev_exp:
                    it["rank_reason"] = "Empate de score/confiança resolvido por menor experiência"
                else:
                    it["rank_reason"] = "Empate técnico resolvido por ordem determinística"
            prev = it

    def _safe_structured(self, resume: Resume | None) -> dict | None:
        if not resume or not resume.structured_json:
            return None
        try:
            data = json.loads(resume.structured_json)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _roles_from_resume(self, resume: Resume | None) -> tuple[str | None, list[str], float | None, bool]:
        if not resume or not resume.structured_json:
            return None, [], None, True
        try:
            data = json.loads(resume.structured_json)
        except Exception:
            return None, [], None, True
        if isinstance(data, dict) and isinstance(data.get("fields"), dict):
            role = (data.get("fields", {}).get("classificacao_cargo") or {})
        else:
            role = (data.get("classificacao_cargo") or {}) if isinstance(data, dict) else {}
        primary = role.get("primary_role") if isinstance(role, dict) else None
        secondary = role.get("secondary_roles") if isinstance(role, dict) else []
        conf = role.get("confidence") if isinstance(role, dict) else None
        role_needs_review = bool(role.get("needs_review")) if isinstance(role, dict) else False
        if not role_needs_review and isinstance(data, dict):
            quality = data.get("quality")
            if isinstance(quality, dict):
                role_needs_review = bool(quality.get("role_classification_needs_review"))
        if not role_needs_review and isinstance(conf, (int, float)):
            role_needs_review = float(conf) < 0.45
        if not isinstance(secondary, list):
            secondary = []
        return (
            str(primary) if primary else None,
            [str(x) for x in secondary[:3]],
            float(conf) if isinstance(conf, (int, float)) else None,
            role_needs_review,
        )
