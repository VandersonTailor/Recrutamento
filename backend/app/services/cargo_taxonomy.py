import re
import unicodedata
import json
from pathlib import Path


ROLE_SYNONYMS: dict[str, list[str]] = {
    "Enfermagem do Trabalho": [
        "tecnico de enfermagem",
        "tecnica de enfermagem",
        "enfermagem do trabalho",
        "tec enfermagem",
        "coren",
        "ambulatorio",
        "saude ocupacional",
        "primeiros socorros",
    ],
    "Motorista": [
        "motorista",
        "condutor",
        "condutora",
        "dirigir onibus",
        "transporte coletivo",
        "cnh d",
        "cnh e",
    ],
    "Auxiliar de Servicos Gerais": [
        "servicos gerais",
        "auxiliar de limpeza",
        "limpeza",
        "conservacao",
        "higienizacao",
    ],
    "Manutencao": [
        "manutencao",
        "mecanico",
        "mecanica",
        "eletrica",
        "eletricista",
        "oficina",
        "chapeador",
        "chapeacao",
        "pintor",
        "pintura",
        "funilaria",
        "preparador",
        "nr10",
        "nr35",
    ],
    "Atendimento": [
        "atendimento",
        "atendente",
        "sac",
        "cliente",
        "bilheteria",
        "recepcao",
    ],
    "Administrativo": [
        "administrativo",
        "assistente administrativo",
        "analista administrativo",
        "rotinas administrativas",
        "office",
        "excel",
    ],
    "TI": [
        "ti",
        "tecnologia da informacao",
        "suporte tecnico",
        "desenvolvedor",
        "programador",
        "python",
        "sql",
        "power bi",
    ],
    "Operacao": [
        "operacao",
        "operador",
        "controle operacional",
        "trafego",
        "frota",
    ],
}

ROLE_REVIEW_MIN_CONFIDENCE = 0.45
ROLE_REVIEW_MIN_MARGIN = 0.08
ROLE_BIAS_MAX_ABS = 0.20
ROLE_FEEDBACK_STEP_CORRECT = 0.03
ROLE_FEEDBACK_STEP_WRONG = 0.02
ROLE_FEEDBACK_PROFILE_PATH = Path(__file__).resolve().parents[2] / "data" / "role_feedback_profile.json"


def classify_roles(text: str, *, top_n: int = 3) -> dict:
    n = _norm(text)
    if not n:
        return {
            "primary_role": None,
            "secondary_roles": [],
            "confidence": 0.0,
            "scores": {},
            "raw_scores": {},
            "top_margin": 0.0,
            "needs_review": True,
            "review_reason": "classificacao_sem_sinal",
        }

    raw_scores: dict[str, float] = {}
    for role, synonyms in ROLE_SYNONYMS.items():
        hits = 0.0
        for syn in synonyms:
            syn_n = _norm(syn)
            if not syn_n:
                continue
            if syn_n in n:
                hits += 1.0
            else:
                syn_parts = [p for p in syn_n.split() if len(p) > 2]
                if syn_parts and all(p in n for p in syn_parts):
                    hits += 0.6
        if hits > 0:
            raw_scores[role] = round(hits / max(1.0, len(synonyms)), 4)

    if not raw_scores:
        return {
            "primary_role": None,
            "secondary_roles": [],
            "confidence": 0.0,
            "scores": {},
            "raw_scores": {},
            "top_margin": 0.0,
            "needs_review": True,
            "review_reason": "classificacao_sem_sinal",
        }

    profile = _read_feedback_profile()
    role_bias = (profile or {}).get("role_bias") if isinstance(profile, dict) else {}
    if not isinstance(role_bias, dict):
        role_bias = {}

    scores: dict[str, float] = {}
    for role, raw_score in raw_scores.items():
        bias = role_bias.get(role, 0.0)
        if not isinstance(bias, (int, float)):
            bias = 0.0
        adjusted = max(0.0, min(1.0, float(raw_score) + float(bias)))
        scores[role] = round(adjusted, 4)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary_role, primary_score = ranked[0]
    secondary = [r for r, _ in ranked[1:top_n]]

    # Confianca alta quando existe destaque do top1 sobre os demais.
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = max(0.0, primary_score - second_score)
    confidence = round(min(0.99, max(0.2, primary_score + margin * 0.5)), 2)
    needs_review = confidence < ROLE_REVIEW_MIN_CONFIDENCE or margin < ROLE_REVIEW_MIN_MARGIN
    review_reason = None
    if needs_review:
        if confidence < ROLE_REVIEW_MIN_CONFIDENCE:
            review_reason = "classificacao_cargo_baixa_confianca"
        elif margin < ROLE_REVIEW_MIN_MARGIN:
            review_reason = "classificacao_cargo_ambigua"

    return {
        "primary_role": primary_role,
        "secondary_roles": secondary,
        "confidence": confidence,
        "scores": scores,
        "raw_scores": raw_scores,
        "top_margin": round(margin, 4),
        "needs_review": needs_review,
        "review_reason": review_reason,
    }


def apply_role_feedback(
    *,
    correct_role: str | None,
    predicted_role: str | None = None,
) -> dict:
    role = _normalize_role_name(correct_role)
    if role is None:
        return _read_feedback_profile()

    pred = _normalize_role_name(predicted_role)
    profile = _read_feedback_profile()
    role_bias = profile.get("role_bias")
    if not isinstance(role_bias, dict):
        role_bias = {}
    stats = profile.get("stats")
    if not isinstance(stats, dict):
        stats = {"total_feedback": 0, "by_role": {}}
    by_role = stats.get("by_role")
    if not isinstance(by_role, dict):
        by_role = {}

    role_bias[role] = _clamp_bias(float(role_bias.get(role, 0.0)) + ROLE_FEEDBACK_STEP_CORRECT)
    if pred and pred != role:
        role_bias[pred] = _clamp_bias(float(role_bias.get(pred, 0.0)) - ROLE_FEEDBACK_STEP_WRONG)

    stats["total_feedback"] = int(stats.get("total_feedback", 0)) + 1
    by_role[role] = int(by_role.get(role, 0)) + 1
    stats["by_role"] = by_role

    out = {"role_bias": role_bias, "stats": stats}
    _write_feedback_profile(out)
    return out


def get_role_feedback_profile() -> dict:
    return _read_feedback_profile()


def _norm(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    raw = re.sub(r"[^a-z0-9\s/\-]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _normalize_role_name(value: str | None) -> str | None:
    n = _norm(value or "")
    if not n:
        return None
    for role in ROLE_SYNONYMS:
        if _norm(role) == n:
            return role
    return None


def _clamp_bias(value: float) -> float:
    return round(max(-ROLE_BIAS_MAX_ABS, min(ROLE_BIAS_MAX_ABS, value)), 6)


def _default_feedback_profile() -> dict:
    return {"role_bias": {}, "stats": {"total_feedback": 0, "by_role": {}}}


def _read_feedback_profile() -> dict:
    try:
        if not ROLE_FEEDBACK_PROFILE_PATH.exists():
            return _default_feedback_profile()
        data = json.loads(ROLE_FEEDBACK_PROFILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_feedback_profile()
        out = _default_feedback_profile()
        role_bias = data.get("role_bias")
        if isinstance(role_bias, dict):
            for key, val in role_bias.items():
                if key in ROLE_SYNONYMS and isinstance(val, (int, float)):
                    out["role_bias"][key] = _clamp_bias(float(val))
        stats = data.get("stats")
        if isinstance(stats, dict):
            out["stats"]["total_feedback"] = int(stats.get("total_feedback", 0))
            by_role = stats.get("by_role")
            if isinstance(by_role, dict):
                out["stats"]["by_role"] = {k: int(v) for k, v in by_role.items() if k in ROLE_SYNONYMS and isinstance(v, (int, float))}
        return out
    except Exception:
        return _default_feedback_profile()


def _write_feedback_profile(profile: dict) -> None:
    try:
        ROLE_FEEDBACK_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROLE_FEEDBACK_PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Falha de persistência não deve quebrar a classificação em runtime.
        return
