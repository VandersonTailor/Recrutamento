import re
import unicodedata

from app.services.cargo_taxonomy import classify_roles


def structure_resume_text(*, text: str, fallback_name: str | None = None) -> dict:
    content = (text or "").strip()
    norm = _norm(content)

    email = _extract_email(content)
    phone = _extract_phone(content)
    city = _extract_city(norm)
    cnh = _extract_cnh(norm)
    availability = _extract_availability(norm)
    schooling = _extract_schooling(norm)
    tech_skills = _extract_tech_skills(norm)
    soft_skills = _extract_soft_skills(norm)
    courses = _extract_courses(content)
    experiences = _extract_experiences(content)
    years = _estimate_years(norm)
    areas = _extract_experience_areas(norm)
    desired_role = _extract_desired_role(content)
    role_classification = classify_roles(content)
    name = _extract_name(content) or fallback_name

    found = 0
    total = 10
    for val in [name, email or phone, city, schooling, courses, experiences, years, tech_skills, cnh, areas]:
        if val:
            if isinstance(val, list) and not val:
                continue
            found += 1

    confidence = round(max(0.05, min(0.99, found / total)), 2)
    reasons: list[str] = []
    if len(content) < 200:
        reasons.append("texto_extraido_muito_curto")
        confidence = min(confidence, 0.35)
    if not email and not phone:
        reasons.append("contato_ausente")
    if not experiences:
        reasons.append("experiencia_nao_detectada")
    if not tech_skills and not soft_skills:
        reasons.append("competencias_nao_detectadas")
    if role_classification.get("needs_review"):
        reasons.append(str(role_classification.get("review_reason") or "classificacao_cargo_baixa_confianca"))

    field_confidence = {
        "nome": _conf(name),
        "contato": max(_conf(email), _conf(phone)),
        "cidade_regiao": _conf(city),
        "escolaridade": _conf(schooling),
        "cursos_certificacoes": _conf(courses),
        "experiencias_profissionais": _conf(experiences),
        "tempo_experiencia_anos": _conf(years),
        "competencias_tecnicas": _conf(tech_skills),
        "competencias_comportamentais": _conf(soft_skills),
        "cnh_categoria": _conf(cnh),
        "disponibilidade_horario": _conf(availability),
        "areas_experiencia": _conf(areas),
        "classificacao_cargo": float(role_classification.get("confidence", 0.0)),
    }

    requires_manual_review = confidence < 0.55 or len(reasons) >= 2 or bool(role_classification.get("needs_review"))

    return {
        "fields": {
            "nome": name,
            "contato": {"email": email, "telefone": phone},
            "cargo_desejado": desired_role,
            "cidade_regiao": city,
            "escolaridade": schooling,
            "cursos_certificacoes": courses,
            "experiencias_profissionais": experiences,
            "tempo_experiencia_anos": years,
            "competencias_tecnicas": tech_skills,
            "competencias_comportamentais": soft_skills,
            "cnh_categoria": cnh,
            "disponibilidade_horario": availability,
            "areas_experiencia": areas,
            "classificacao_cargo": role_classification,
        },
        "quality": {
            "confidence": confidence,
            "field_confidence": field_confidence,
            "requires_manual_review": requires_manual_review,
            "review_reason": ";".join(reasons) if reasons else None,
            "role_classification_needs_review": bool(role_classification.get("needs_review")),
            "role_review_reason": role_classification.get("review_reason"),
        },
    }


def _norm(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    raw = re.sub(r"[^a-z0-9\s/\-]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _extract_email(text: str) -> str | None:
    m = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text or "", flags=re.IGNORECASE)
    return m.group(0).lower().strip() if m else None


def _extract_phone(text: str) -> str | None:
    m = re.search(r"(\+\d{1,3}\s*)?(\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}", text or "")
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(0))
    return digits[-13:] if len(digits) > 13 else digits


def _extract_city(norm: str) -> str | None:
    cities = [
        "porto alegre",
        "canoas",
        "viamao",
        "alvorada",
        "gravatai",
        "sao leopoldo",
        "novo hamburgo",
        "cachoeirinha",
    ]
    for city in cities:
        if city in norm:
            return city.title()
    return None


def _extract_name(text: str) -> str | None:
    # Prioriza padrões explícitos: "NOME: Fulano de Tal"
    explicit = re.search(r"\bnome\s*[:\-]\s*([A-Za-zÀ-ÿ' ]{5,120})", text or "", flags=re.IGNORECASE)
    if explicit:
        name = explicit.group(1).strip(" .,-")
        if _is_valid_name(name):
            return name

    for line in text.splitlines():
        s = line.strip()
        if not (4 <= len(s) <= 80):
            continue
        if ":" in s and len(s.split(":")[0]) > 2:
            # Linhas como "Experiência: ..." ou "Objetivo: ..." não são nome.
            continue
        if "@" in s or any(ch.isdigit() for ch in s):
            continue
        low = _norm(s)
        if any(k in low for k in ["curriculo", "resumo", "experiencia", "objetivo", "cargo"]):
            continue
        if _is_valid_name(s):
            return s
    return None


def _extract_desired_role(text: str) -> str | None:
    for line in text.splitlines()[:20]:
        s = line.strip()
        if not s:
            continue
        low = _norm(s)
        if any(k in low for k in ["objetivo", "cargo", "funcao", "vaga"]):
            return s
    return None


def _extract_schooling(norm: str) -> list[str]:
    labels = [
        "ensino medio",
        "ensino fundamental",
        "ensino tecnico",
        "ensino superior",
        "graduacao",
        "pos graduacao",
        "tecnologo",
    ]
    return [x for x in labels if x in norm]


def _extract_courses(text: str) -> list[str]:
    hits = []
    patterns = [
        r"\bnr ?10\b",
        r"\bnr ?35\b",
        r"\bcnh [abcdex]\b",
        r"\bexcel\b",
        r"\bpower ?bi\b",
        r"\bpython\b",
        r"\bsql\b",
    ]
    t = _norm(text)
    for p in patterns:
        if re.search(p, t):
            hits.append(re.sub(r"\\b", "", p).replace("?", "").replace("\\", "").strip())
    return sorted(set(hits))


def _extract_tech_skills(norm: str) -> list[str]:
    skills = [
        "excel",
        "power bi",
        "python",
        "sql",
        "sap",
        "mecanica",
        "eletrica",
        "atendimento",
        "office",
        "word",
    ]
    return [s for s in skills if s in norm]


def _extract_soft_skills(norm: str) -> list[str]:
    soft = [
        "comunicacao",
        "organizacao",
        "proatividade",
        "lideranca",
        "trabalho em equipe",
        "responsabilidade",
        "pontualidade",
    ]
    return [s for s in soft if s in norm]


def _extract_cnh(norm: str) -> str | None:
    m = re.search(r"\bcnh\s*([abcdex])\b", norm)
    if m:
        return m.group(1).upper()
    m2 = re.search(r"\bcategoria\s*([abcdex])\b", norm)
    if m2:
        return m2.group(1).upper()
    return None


def _extract_availability(norm: str) -> str | None:
    if "disponibilidade de horario" in norm or "turno" in norm or "escala" in norm:
        return "Disponível"
    return None


def _estimate_years(norm: str) -> float | None:
    m = re.search(r"(\d{1,2})\s+anos?", norm)
    if m:
        return float(m.group(1))
    return None


def _extract_experience_areas(norm: str) -> list[str]:
    areas = [
        (r"\batendimento\b", "atendimento"),
        (r"\boperac(?:ao|oes|ional|or)\b", "operacao"),
        (r"\bmanutenc(?:ao|oes)\b", "manutencao"),
        (r"\boficina\b", "oficina"),
        (r"\badministrativ", "administracao"),
        (r"\btecnologia da informacao\b|\bti\b", "ti"),
        (r"\btransporte\b|\bonibus\b|\bfrota\b", "transporte"),
    ]
    out = []
    for pattern, label in areas:
        if re.search(pattern, norm):
            out.append(label)
    return sorted(set(out))


def _extract_experiences(text: str) -> list[dict]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: list[dict] = []
    for ln in lines:
        n = _norm(ln)
        if any(k in n for k in ["experiencia", "trabalhou", "atuou", "empresa", "cargo"]):
            out.append({"descricao": ln})
        if len(out) >= 6:
            break
    return out


def _conf(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, str):
        return 0.9 if value.strip() else 0.0
    if isinstance(value, (int, float)):
        return 0.9
    if isinstance(value, list):
        return min(0.95, 0.3 + 0.2 * len(value)) if value else 0.0
    if isinstance(value, dict):
        return 0.6 if value else 0.0
    return 0.0


def _is_valid_name(value: str | None) -> bool:
    if not value:
        return False
    s = value.strip()
    if len(s.split()) < 2:
        return False
    n = _norm(s)
    blocked = {"semnome", "sem nome", "desconhecido", "nao informado", "não informado"}
    if n in blocked:
        return False
    noisy_fragments = (
        "sobre mim",
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
        return False
    return True
