import json
from copy import deepcopy

from app.models.job import Job
from app.services.cargo_taxonomy import classify_roles


DEFAULT_SCORING_PROFILE: dict = {
    "weights": {
        "cargo": 0.30,
        "formacao": 0.20,
        "cursos": 0.25,
        "experiencia": 0.25,
    },
    "porto_alegre_bonus": 8.0,
    "minimum_signal_floor": 12.0,
    "ranking_filters": {
        "required_courses": [],
        "minimum_years_experience": 0.0,
        "preferred_cities": [],
        "residence_required": False,
        "custom_filters": [],
    },
}

ROLE_SCORING_PROFILES: dict[str, dict] = {
    "Motorista": {
        "weights": {"cargo": 0.35, "formacao": 0.10, "cursos": 0.20, "experiencia": 0.35},
        "porto_alegre_bonus": 10.0,
        "minimum_signal_floor": 14.0,
    },
    "Manutencao": {
        "weights": {"cargo": 0.30, "formacao": 0.15, "cursos": 0.30, "experiencia": 0.25},
        "porto_alegre_bonus": 8.0,
        "minimum_signal_floor": 12.0,
    },
    "Atendimento": {
        "weights": {"cargo": 0.30, "formacao": 0.20, "cursos": 0.20, "experiencia": 0.30},
        "porto_alegre_bonus": 8.0,
        "minimum_signal_floor": 11.0,
    },
    "Administrativo": {
        "weights": {"cargo": 0.25, "formacao": 0.25, "cursos": 0.20, "experiencia": 0.30},
        "porto_alegre_bonus": 6.0,
        "minimum_signal_floor": 10.0,
    },
    "TI": {
        "weights": {"cargo": 0.35, "formacao": 0.15, "cursos": 0.25, "experiencia": 0.25},
        "porto_alegre_bonus": 6.0,
        "minimum_signal_floor": 10.0,
    },
}


def read_scoring_profile(job: Job) -> dict:
    role = _infer_role_from_job(job.title or "")
    profile = deepcopy(ROLE_SCORING_PROFILES.get(role, DEFAULT_SCORING_PROFILE))
    profile["role_hint"] = role
    if not isinstance(profile.get("ranking_filters"), dict):
        profile["ranking_filters"] = deepcopy(DEFAULT_SCORING_PROFILE["ranking_filters"])
    raw = (job.ranking_profile or "").strip()
    if not raw:
        return profile

    try:
        incoming = json.loads(raw)
    except Exception:
        return profile

    if not isinstance(incoming, dict):
        return profile

    weights = incoming.get("weights")
    if isinstance(weights, dict):
        normalized = _normalize_weights(weights)
        if normalized:
            profile["weights"] = normalized

    bonus = incoming.get("porto_alegre_bonus")
    if isinstance(bonus, (int, float)):
        profile["porto_alegre_bonus"] = float(max(0.0, min(25.0, bonus)))

    floor = incoming.get("minimum_signal_floor")
    if isinstance(floor, (int, float)):
        profile["minimum_signal_floor"] = float(max(0.0, min(40.0, floor)))

    filters = _normalize_ranking_filters(incoming.get("ranking_filters"))
    if filters is not None:
        profile["ranking_filters"] = filters

    return profile


def store_scoring_profile(job: Job, payload: dict) -> dict:
    role = _infer_role_from_job(job.title or "")
    profile = deepcopy(ROLE_SCORING_PROFILES.get(role, DEFAULT_SCORING_PROFILE))
    profile["role_hint"] = role
    if not isinstance(profile.get("ranking_filters"), dict):
        profile["ranking_filters"] = deepcopy(DEFAULT_SCORING_PROFILE["ranking_filters"])
    if not isinstance(payload, dict):
        payload = {}

    weights = payload.get("weights")
    if isinstance(weights, dict):
        normalized = _normalize_weights(weights)
        if normalized:
            profile["weights"] = normalized

    bonus = payload.get("porto_alegre_bonus")
    if isinstance(bonus, (int, float)):
        profile["porto_alegre_bonus"] = float(max(0.0, min(25.0, bonus)))

    floor = payload.get("minimum_signal_floor")
    if isinstance(floor, (int, float)):
        profile["minimum_signal_floor"] = float(max(0.0, min(40.0, floor)))

    filters = _normalize_ranking_filters(payload.get("ranking_filters"))
    if filters is not None:
        profile["ranking_filters"] = filters

    job.ranking_profile = json.dumps(profile, ensure_ascii=False)
    return profile


def apply_feedback_to_profile(*, profile: dict, signal: dict, decision: str, alpha: float = 0.12) -> dict:
    out = deepcopy(profile if isinstance(profile, dict) else DEFAULT_SCORING_PROFILE)
    weights = dict(out.get("weights") or {})
    if not weights:
        weights = dict(DEFAULT_SCORING_PROFILE["weights"])

    sig = _normalize_feedback_signal(signal)
    if not sig:
        return out

    d = (decision or "").strip().lower()
    if d in {"approved", "promoted"}:
        target = sig
    elif d in {"rejected"}:
        inv = {k: max(0.0, 1.0 - v) for k, v in sig.items()}
        target = _normalize_weights(inv) or sig
    else:
        return out

    new_w = {}
    for k in ("cargo", "formacao", "cursos", "experiencia"):
        cur = float(weights.get(k, DEFAULT_SCORING_PROFILE["weights"][k]))
        tgt = float(target.get(k, cur))
        new_w[k] = (1.0 - alpha) * cur + alpha * tgt
    new_w = _normalize_weights(new_w) or DEFAULT_SCORING_PROFILE["weights"]
    out["weights"] = new_w

    stats = out.get("feedback_stats")
    if not isinstance(stats, dict):
        stats = {"approved": 0, "promoted": 0, "rejected": 0}
    if d in stats:
        stats[d] = int(stats.get(d, 0)) + 1
    out["feedback_stats"] = stats
    return out


def _normalize_weights(weights: dict) -> dict | None:
    keys = ("cargo", "formacao", "cursos", "experiencia")
    out: dict[str, float] = {}
    for key in keys:
        value = weights.get(key)
        if isinstance(value, (int, float)):
            out[key] = float(max(0.0, value))

    total = sum(out.values())
    if total <= 0:
        return None

    return {k: round(v / total, 6) for k, v in out.items()}


def _infer_role_from_job(title: str) -> str | None:
    classified = classify_roles(title or "")
    return classified.get("primary_role")


def _normalize_feedback_signal(signal: dict) -> dict | None:
    if not isinstance(signal, dict):
        return None
    base = {}
    for key in ("cargo", "formacao", "cursos", "experiencia"):
        val = signal.get(key)
        if isinstance(val, (int, float)):
            base[key] = max(0.0, min(1.0, float(val)))
    if not base:
        return None
    return _normalize_weights(base)


def _normalize_ranking_filters(raw: dict | None) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None

    def _as_clean_str_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            s = item.strip()
            if s:
                out.append(s[:120])
        return out[:50]

    minimum_years_experience = raw.get("minimum_years_experience")
    if isinstance(minimum_years_experience, (int, float)):
        min_years = float(max(0.0, min(60.0, minimum_years_experience)))
    else:
        min_years = 0.0

    custom_filters_raw = raw.get("custom_filters")
    custom_filters: list[dict] = []
    if isinstance(custom_filters_raw, list):
        for item in custom_filters_raw[:20]:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            if not isinstance(label, str) or not label.strip():
                continue
            keywords = _as_clean_str_list(item.get("keywords"))
            mode = (item.get("mode") or "bonus")
            mode = str(mode).strip().lower()
            if mode not in {"bonus", "required"}:
                mode = "bonus"
            points_raw = item.get("points")
            points = float(points_raw) if isinstance(points_raw, (int, float)) else 3.0
            points = float(max(0.0, min(20.0, points)))
            custom_filters.append(
                {
                    "label": label.strip()[:120],
                    "keywords": keywords,
                    "mode": mode,
                    "points": points,
                }
            )

    return {
        "required_courses": _as_clean_str_list(raw.get("required_courses")),
        "minimum_years_experience": min_years,
        "preferred_cities": _as_clean_str_list(raw.get("preferred_cities")),
        "residence_required": bool(raw.get("residence_required")),
        "custom_filters": custom_filters,
    }
