import re
import unicodedata
from dataclasses import dataclass

from app.models.application import Application
from app.models.job import Job


@dataclass(frozen=True)
class MatchBreakdown:
    cargo: float
    formacao: float
    cursos: float
    experiencia: float
    localizacao_bonus: float
    stuffing_penalty: float
    consistencia_bonus: float
    simple_profile_bonus: float
    total: float
    highlights: list[str]


def compute_match(
    application: Application,
    job: Job,
    *,
    resume_text: str | None = None,
    candidate_address: str | None = None,
    scoring_profile: dict | None = None,
    resume_structured: dict | None = None,
) -> MatchBreakdown:
    # Base textual mais robusta (evita score zerado quando analysis_json vem vazio).
    text_job = " ".join(
        [
            job.title or "",
            job.description or "",
            job.requirements or "",
        ]
    )
    text_app = " ".join(
        [
            application.analysis_json or "",
            application.score_justification or "",
            application.strengths or "",
            application.concerns or "",
            application.seniority or "",
            resume_text or "",
        ]
    )

    tokens_job = _tokenize(text_job)
    tokens_app = _tokenize(text_app)
    overlap = _overlap_ratio(tokens_job, tokens_app)
    cargo = min(1.0, overlap)

    # Formação/cursos/experiência — heurísticas por palavras-chave
    form_words = {"ensino", "superior", "tecnologo", "graduacao", "faculdade", "tecnico"}
    course_words = {"curso", "certificacao", "nr10", "nr35", "cnh", "excel", "python", "powerbi", "sql"}
    exp_words = {"experiencia", "anos", "tempo", "atuacao", "trabalhou", "projeto"}

    def score_for(words: set[str]) -> float:
        ntext = _norm(text_app)
        hits = sum(1 for w in words if w in ntext)
        return min(1.0, hits / max(1, len(words)))

    formacao = score_for(form_words)
    cursos = score_for(course_words)
    experiencia = score_for(exp_words)

    profile = scoring_profile or {}
    weights = profile.get("weights") if isinstance(profile, dict) else {}
    w_cargo = float((weights or {}).get("cargo", 0.30))
    w_formacao = float((weights or {}).get("formacao", 0.20))
    w_cursos = float((weights or {}).get("cursos", 0.25))
    w_experiencia = float((weights or {}).get("experiencia", 0.25))

    base_total = (
        cargo * w_cargo
        + formacao * w_formacao
        + cursos * w_cursos
        + experiencia * w_experiencia
    ) * 100.0

    # Bônus de localização para Porto Alegre (pedido de negócio).
    porto_alegre_bonus = 0.0
    configured_bonus = float(profile.get("porto_alegre_bonus", 8.0)) if isinstance(profile, dict) else 8.0
    if _is_porto_alegre(candidate_address or "") or _is_porto_alegre((resume_text or "")[:2000]):
        porto_alegre_bonus = configured_bonus

    # Piso de score para evitar quase tudo zerado quando há evidência textual mínima.
    has_signal = bool(tokens_app) and (cargo > 0 or formacao > 0 or cursos > 0 or experiencia > 0)
    floor_cfg = float(profile.get("minimum_signal_floor", 12.0)) if isinstance(profile, dict) else 12.0
    floor = floor_cfg if has_signal else 0.0
    stuffing_penalty = _keyword_stuffing_penalty(text_app, tokens_job)
    consistencia_bonus = _consistency_bonus(resume_structured)
    simple_profile_bonus = _simple_profile_bonus(resume_structured)
    filters_bonus, filters_penalty, filter_highlights = _evaluate_ranking_filters(
        profile=profile,
        app=application,
        text_app=text_app,
        candidate_address=candidate_address,
    )
    total = min(
        100.0,
        max(
            0.0,
            max(base_total, floor)
            + porto_alegre_bonus
            + consistencia_bonus
            + simple_profile_bonus
            + filters_bonus
            - stuffing_penalty
            - filters_penalty,
        ),
    )

    highlights: list[str] = []
    aj = (text_app or "").lower()
    if "cnh d" in aj or "cnh(de" in aj or "cnh (d" in aj:
        highlights.append("CNH categoria D")
    if "nr10" in aj:
        highlights.append("Certificação NR10")
    if "nr35" in aj:
        highlights.append("Certificação NR35")
    if porto_alegre_bonus > 0:
        highlights.append("Reside em Porto Alegre (+8)")
    if stuffing_penalty > 0:
        highlights.append(f"Penalidade por repetição de palavras-chave (-{int(round(stuffing_penalty))})")
    if consistencia_bonus > 0:
        highlights.append(f"Bônus de consistência de currículo (+{int(round(consistencia_bonus))})")
    if simple_profile_bonus > 0:
        highlights.append(f"Bônus por evidência forte em currículo simples (+{int(round(simple_profile_bonus))})")
    highlights.extend(filter_highlights)

    return MatchBreakdown(
        cargo=cargo * 100.0,
        formacao=formacao * 100.0,
        cursos=cursos * 100.0,
        experiencia=experiencia * 100.0,
        localizacao_bonus=porto_alegre_bonus,
        stuffing_penalty=stuffing_penalty,
        consistencia_bonus=consistencia_bonus,
        simple_profile_bonus=simple_profile_bonus,
        total=total,
        highlights=highlights,
    )


def _evaluate_ranking_filters(*, profile: dict, app: Application, text_app: str, candidate_address: str | None) -> tuple[float, float, list[str]]:
    ranking_filters = profile.get("ranking_filters") if isinstance(profile, dict) else None
    if not isinstance(ranking_filters, dict):
        return 0.0, 0.0, []

    norm_text = _norm(text_app)
    bonus = 0.0
    penalty = 0.0
    highlights: list[str] = []

    required_courses = ranking_filters.get("required_courses")
    if isinstance(required_courses, list) and required_courses:
        courses = [str(c).strip().lower() for c in required_courses if str(c).strip()]
        if courses:
            matched = [course for course in courses if _norm(course) in norm_text]
            coverage = len(matched) / len(courses)
            if matched:
                gained = min(8.0, 2.0 + (coverage * 6.0))
                bonus += gained
                highlights.append(f"Cursos obrigatórios atendidos (+{int(round(gained))})")
            else:
                penalty += 10.0
                highlights.append("Cursos obrigatórios não encontrados (-10)")

    min_years_raw = ranking_filters.get("minimum_years_experience")
    if isinstance(min_years_raw, (int, float)) and float(min_years_raw) > 0:
        min_years = float(min_years_raw)
        years = float(app.experience_years or 0.0)
        if years >= min_years:
            gained = min(6.0, 2.0 + min(4.0, years - min_years))
            bonus += gained
            highlights.append(f"Experiência mínima atendida (+{int(round(gained))})")
        else:
            gap = min_years - years
            loss = min(12.0, 3.0 + gap * 2.0)
            penalty += loss
            highlights.append(f"Experiência abaixo do mínimo (-{int(round(loss))})")

    preferred_cities = ranking_filters.get("preferred_cities")
    residence_required = bool(ranking_filters.get("residence_required"))
    if isinstance(preferred_cities, list) and preferred_cities:
        cities = [str(c).strip().lower() for c in preferred_cities if str(c).strip()]
        addr = _norm(candidate_address or "")
        has_city_match = any(_norm(city) in addr for city in cities)
        if has_city_match:
            bonus += 4.0
            highlights.append("Residência alinhada à vaga (+4)")
        elif residence_required:
            penalty += 10.0
            highlights.append("Residência fora do critério obrigatório (-10)")

    custom_filters = ranking_filters.get("custom_filters")
    if isinstance(custom_filters, list):
        for rule in custom_filters[:20]:
            if not isinstance(rule, dict):
                continue
            label = str(rule.get("label") or "").strip()
            if not label:
                continue
            mode = str(rule.get("mode") or "bonus").strip().lower()
            points_raw = rule.get("points")
            points = float(points_raw) if isinstance(points_raw, (int, float)) else 3.0
            points = max(0.0, min(20.0, points))
            keywords = rule.get("keywords")
            kw_list = [str(k).strip().lower() for k in keywords] if isinstance(keywords, list) else []
            kw_list = [k for k in kw_list if k]
            if not kw_list:
                continue
            matched = any(_norm(k) in norm_text for k in kw_list)
            if mode == "required":
                if matched:
                    bonus += min(points, 8.0)
                    highlights.append(f"{label}: requisito atendido (+{int(round(min(points, 8.0)))})")
                else:
                    penalty += points
                    highlights.append(f"{label}: requisito ausente (-{int(round(points))})")
            elif matched:
                bonus += points
                highlights.append(f"{label}: evidência encontrada (+{int(round(points))})")

    return round(bonus, 2), round(penalty, 2), highlights[:8]


def _norm(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    raw = re.sub(r"[^a-z0-9\s\+\#\.]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _tokenize(value: str) -> set[str]:
    norm = _norm(value)
    if not norm:
        return set()
    return set(re.findall(r"[a-z0-9\+\#\.]{2,}", norm))


def _overlap_ratio(job_tokens: set[str], app_tokens: set[str]) -> float:
    if not job_tokens or not app_tokens:
        return 0.0
    hits = 0.0
    for jt in job_tokens:
        if jt in app_tokens:
            hits += 1.0
            continue
        if len(jt) >= 5 and any(at.startswith(jt[:5]) or jt.startswith(at[:5]) for at in app_tokens if len(at) >= 5):
            hits += 0.6
    return min(1.0, hits / max(1.0, float(len(job_tokens))))


def _is_porto_alegre(value: str) -> bool:
    n = _norm(value)
    if not n:
        return False
    if "porto alegre" in n:
        return True
    if re.search(r"\bpoa\b", n):
        return True
    if re.search(r"\bporto alegre\s*/\s*rs\b", n):
        return True
    if re.search(r"\bporto alegre\b.*\brs\b", n):
        return True
    return False


def _keyword_stuffing_penalty(text: str, job_tokens: set[str]) -> float:
    tokens = re.findall(r"[a-z0-9\+\#\.]{2,}", _norm(text))
    if len(tokens) < 40:
        return 0.0
    if not job_tokens:
        return 0.0
    freq: dict[str, int] = {}
    for t in tokens:
        if t in job_tokens:
            freq[t] = freq.get(t, 0) + 1
    if not freq:
        return 0.0
    max_rep = max(freq.values())
    unique_ratio = len(set(tokens)) / max(1.0, float(len(tokens)))
    repeated_job_tokens = sum(1 for _, v in freq.items() if v >= 6)

    penalty = 0.0
    if max_rep >= 12:
        penalty += min(10.0, (max_rep - 11) * 0.8)
    if unique_ratio < 0.22:
        penalty += min(6.0, (0.22 - unique_ratio) * 40.0)
    if repeated_job_tokens >= 3:
        penalty += min(4.0, (repeated_job_tokens - 2) * 1.2)
    return round(min(18.0, penalty), 2)


def _consistency_bonus(resume_structured: dict | None) -> float:
    if not isinstance(resume_structured, dict):
        return 0.0
    quality = resume_structured.get("quality")
    if not isinstance(quality, dict):
        return 0.0
    conf = quality.get("confidence")
    if not isinstance(conf, (int, float)):
        return 0.0
    # Evita punir currículo simples: boa consistência estrutural recebe bônus leve.
    if conf >= 0.8:
        return 4.0
    if conf >= 0.65:
        return 2.0
    return 0.0


def _simple_profile_bonus(resume_structured: dict | None) -> float:
    # Evita penalizar candidato bom com currículo objetivo/simples.
    if not isinstance(resume_structured, dict):
        return 0.0
    fields = resume_structured.get("fields")
    quality = resume_structured.get("quality")
    if not isinstance(fields, dict) or not isinstance(quality, dict):
        return 0.0

    conf = quality.get("confidence")
    if not isinstance(conf, (int, float)):
        return 0.0
    # Aplica quando confiança geral está média/baixa, mas há sinais fortes.
    if conf >= 0.65:
        return 0.0

    evidences = 0
    exp = fields.get("tempo_experiencia_anos")
    if isinstance(exp, (int, float)) and exp >= 2:
        evidences += 1
    cnh = fields.get("cnh_categoria")
    if isinstance(cnh, str) and cnh.strip():
        evidences += 1
    areas = fields.get("areas_experiencia")
    if isinstance(areas, list) and len(areas) >= 1:
        evidences += 1
    exps = fields.get("experiencias_profissionais")
    if isinstance(exps, list) and len(exps) >= 1:
        evidences += 1

    if evidences >= 3:
        return 3.0
    if evidences == 2:
        return 1.5
    return 0.0
