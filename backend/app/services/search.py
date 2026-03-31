import re
import json
import math
import unicodedata
from collections import Counter

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.resume import Resume


class SearchService:
    def __init__(self, db: Session):
        self.db = db

    def search(self, query: str, *, limit: int = 50) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []

        years = _extract_years(q)
        tokens = _extract_tokens(q)

        stmt = (
            select(Application, Candidate, Job)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
        )

        clauses = []
        for t in tokens:
            like = f"%{t}%"
            clauses.append(Candidate.full_name.ilike(like))
            clauses.append(Job.title.ilike(like))
            clauses.append(Application.analysis_json.ilike(like))

        if clauses:
            stmt = stmt.where(or_(*clauses))

        if years is not None:
            stmt = stmt.where(and_(Application.experience_years.is_not(None), Application.experience_years >= years))

        stmt = stmt.order_by(Application.score.desc().nullslast(), Application.updated_at.desc()).limit(limit)
        rows = self.db.execute(stmt).all()

        out: list[dict] = []
        for app, cand, job in rows:
            out.append(
                {
                    "application_id": app.id,
                    "candidate_id": cand.id,
                    "candidate_name": cand.full_name,
                    "job_id": job.id,
                    "job_title": job.title,
                    "stage": app.stage,
                    "score": app.score,
                    "experience_years": app.experience_years,
                    "seniority": app.seniority,
                }
            )
        return out

    def semantic_search(
        self,
        query: str,
        *,
        limit: int = 30,
        min_score: float = 0.15,
        department: str | None = None,
    ) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        qv = _vectorize(q)
        if not qv:
            return []

        stmt = (
            select(Application, Candidate, Job)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .order_by(Application.updated_at.desc())
            .limit(800)
        )
        if department:
            stmt = stmt.join(Resume, Resume.candidate_id == Application.candidate_id).where(Resume.department == department)
        rows = self.db.execute(stmt).all()

        out: list[dict] = []
        for app, cand, job in rows:
            resume = self._latest_resume_for_candidate(candidate_id=cand.id)
            profile = self._candidate_profile_text(cand=cand, app=app, resume=resume, job=job)
            score, overlap = _semantic_score_from_vectors(qv, _vectorize(profile))
            if score < min_score:
                continue
            out.append(
                {
                    "application_id": app.id,
                    "candidate_id": cand.id,
                    "candidate_name": cand.full_name,
                    "job_id": job.id,
                    "job_title": job.title,
                    "stage": app.stage,
                    "score": app.score,
                    "semantic_score": round(score, 4),
                    "matched_terms": overlap[:8],
                }
            )
        out.sort(key=lambda x: (x.get("semantic_score", 0.0), x.get("score") or 0.0), reverse=True)
        return out[:limit]

    def detect_duplicate_candidates(
        self,
        *,
        limit: int = 50,
        threshold: float = 0.72,
        max_candidates: int = 250,
        department: str | None = None,
    ) -> list[dict]:
        latest = self._latest_resume_per_candidate(limit=max_candidates, department=department)
        pool: list[dict] = []
        for cand, resume in latest:
            profile = self._candidate_profile_text(cand=cand, app=None, resume=resume, job=None)
            pool.append(
                {
                    "candidate_id": cand.id,
                    "candidate_name": cand.full_name,
                    "email": cand.email,
                    "phone": cand.phone,
                    "profile": profile,
                    "vector": _vectorize(profile),
                }
            )

        out: list[dict] = []
        for i in range(len(pool)):
            a = pool[i]
            for j in range(i + 1, len(pool)):
                b = pool[j]
                score, overlap = _semantic_score_from_vectors(a["vector"], b["vector"])
                if a.get("email") and b.get("email") and str(a["email"]).lower() == str(b["email"]).lower():
                    score = max(score, 0.98)
                if a.get("phone") and b.get("phone") and _digits(a["phone"]) == _digits(b["phone"]):
                    score = max(score, 0.98)
                if score < threshold:
                    continue
                out.append(
                    {
                        "candidate_a_id": a["candidate_id"],
                        "candidate_a_name": a["candidate_name"],
                        "candidate_b_id": b["candidate_id"],
                        "candidate_b_name": b["candidate_name"],
                        "similarity": round(score, 4),
                        "matched_terms": overlap[:10],
                        "signals": {
                            "same_email": bool(a.get("email") and b.get("email") and str(a["email"]).lower() == str(b["email"]).lower()),
                            "same_phone": bool(a.get("phone") and b.get("phone") and _digits(a["phone"]) == _digits(b["phone"])),
                        },
                    }
                )
        out.sort(key=lambda x: x["similarity"], reverse=True)
        return out[:limit]

    def recommend_candidates_for_job(
        self,
        *,
        job_id: int,
        limit: int = 30,
        min_score: float = 0.18,
        include_existing_applications: bool = False,
    ) -> list[dict]:
        job = self.db.get(Job, job_id)
        if not job:
            return []
        target_text = " ".join(
            [
                job.title or "",
                job.description or "",
                job.requirements or "",
                job.department or "",
            ]
        ).strip()
        jv = _vectorize(target_text)
        if not jv:
            return []

        latest = self._latest_resume_per_candidate(limit=1000, department=job.department)
        out: list[dict] = []
        for cand, resume in latest:
            if not include_existing_applications:
                exists = (
                    self.db.execute(
                        select(Application.id)
                        .where(Application.candidate_id == cand.id, Application.job_id == job_id)
                        .limit(1)
                    ).first()
                    is not None
                )
                if exists:
                    continue
            profile = self._candidate_profile_text(cand=cand, app=None, resume=resume, job=None)
            score, overlap = _semantic_score_from_vectors(jv, _vectorize(profile))
            if score < min_score:
                continue
            years = _extract_years(profile)
            out.append(
                {
                    "candidate_id": cand.id,
                    "candidate_name": cand.full_name,
                    "job_id": job_id,
                    "job_title": job.title,
                    "semantic_score": round(score, 4),
                    "estimated_experience_years": years,
                    "matched_terms": overlap[:10],
                    "source_department": resume.department if resume else None,
                }
            )
        out.sort(key=lambda x: (x["semantic_score"], x.get("estimated_experience_years") or 0.0), reverse=True)
        return out[:limit]

    def _latest_resume_for_candidate(self, *, candidate_id: int) -> Resume | None:
        return (
            self.db.execute(
                select(Resume)
                .where(Resume.candidate_id == candidate_id)
                .order_by(Resume.received_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def _latest_resume_per_candidate(self, *, limit: int, department: str | None = None) -> list[tuple[Candidate, Resume | None]]:
        stmt = select(Candidate).order_by(Candidate.created_at.desc()).limit(limit)
        candidates = list(self.db.execute(stmt).scalars().all())
        out: list[tuple[Candidate, Resume | None]] = []
        for cand in candidates:
            r_stmt = select(Resume).where(Resume.candidate_id == cand.id).order_by(Resume.received_at.desc()).limit(1)
            if department:
                r_stmt = select(Resume).where(Resume.candidate_id == cand.id, Resume.department == department).order_by(Resume.received_at.desc()).limit(1)
            resume = self.db.execute(r_stmt).scalars().first()
            out.append((cand, resume))
        return out

    def _candidate_profile_text(
        self,
        *,
        cand: Candidate,
        app: Application | None,
        resume: Resume | None,
        job: Job | None,
    ) -> str:
        chunks = [cand.full_name or "", cand.email or "", cand.phone or "", cand.address or ""]
        if app:
            chunks.extend(
                [
                    app.analysis_json or "",
                    app.score_justification or "",
                    app.strengths or "",
                    app.concerns or "",
                    app.seniority or "",
                    app.primary_role or "",
                ]
            )
        if resume:
            chunks.extend(
                [
                    resume.extracted_text or "",
                    resume.structured_json or "",
                    resume.department or "",
                ]
            )
        if job:
            chunks.extend([job.title or "", job.department or ""])
        return " ".join(chunks)


def _extract_years(query: str) -> float | None:
    m = re.search(r"(\d+(?:[\\.,]\\d+)?)\\s*anos?", query, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None


def _extract_tokens(query: str) -> list[str]:
    tokens = re.findall(r"[\\wÀ-ÿ\\+\\#\\.]{2,}", query, flags=re.IGNORECASE)
    cleaned: list[str] = []
    for t in tokens:
        tl = t.lower()
        if tl in {"anos", "ano", "com", "de", "em", "para", "e", "ou"}:
            continue
        cleaned.append(t)
    return cleaned[:10]


def _norm(text: str) -> str:
    raw = (text or "").strip().lower()
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    raw = re.sub(r"[^a-z0-9\s]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _vectorize(text: str) -> Counter:
    normalized = _norm(_json_to_text(text))
    if not normalized:
        return Counter()
    stopwords = {
        "de",
        "da",
        "do",
        "dos",
        "das",
        "e",
        "ou",
        "em",
        "para",
        "com",
        "anos",
        "ano",
        "curriculo",
    }
    tokens = [t for t in normalized.split() if len(t) >= 2 and t not in stopwords]
    return Counter(tokens)


def _semantic_score_from_vectors(a: Counter, b: Counter) -> tuple[float, list[str]]:
    if not a or not b:
        return 0.0, []
    common = set(a.keys()).intersection(b.keys())
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0, []
    cosine = dot / (norm_a * norm_b)
    overlap = sorted(common, key=lambda t: min(a[t], b[t]), reverse=True)
    return max(0.0, min(1.0, cosine)), overlap


def _json_to_text(raw: str) -> str:
    try:
        if not raw or not isinstance(raw, str):
            return raw or ""
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return " ".join(_flatten_values(parsed))
        if isinstance(parsed, list):
            return " ".join(_flatten_values(parsed))
        return raw
    except Exception:
        return raw


def _flatten_values(value) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_values(v))
        return out
    if isinstance(value, list):
        for v in value:
            out.extend(_flatten_values(v))
        return out
    if value is None:
        return out
    out.append(str(value))
    return out


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))
