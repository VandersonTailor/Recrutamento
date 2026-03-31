import re
import unicodedata
from datetime import datetime
from pathlib import Path


def parse_resume_filename(filename: str) -> dict:
    stem = Path(filename).stem
    out = {"cargo": None, "cnh": None, "nome": None, "data": None}

    # Ex: motorista-cnh_d-carlos_henrique-21-03-2026.pdf
    m = re.match(
        r"^(?P<cargo>.+?)-(?P<cnh>cnh[_-]?[a-z0-9]+)-(?P<nome>.+)-(?P<data>\d{2}-\d{2}-\d{4})$",
        stem,
        flags=re.IGNORECASE,
    )
    if m:
        out["cargo"] = _humanize_token(m.group("cargo"))
        out["cnh"] = _normalize_cnh(m.group("cnh"))
        out["nome"] = _humanize_token(m.group("nome"))
        out["data"] = m.group("data")
        return out

    # Legado: cargo-CNH(D)-nome-21-03-2026
    m = re.match(
        r"^(?P<cargo>.+?)-(?:PCD-)?CNH\((?P<cnh>[^)]*)\)-(?P<nome>.+)-(?P<data>\d{2}-\d{2}-\d{4})$",
        stem,
        flags=re.IGNORECASE,
    )
    if m:
        out["cargo"] = _humanize_token(m.group("cargo"))
        out["cnh"] = _normalize_cnh(m.group("cnh"))
        out["nome"] = _humanize_token(m.group("nome"))
        out["data"] = m.group("data")
        return out

    parts = stem.split("-")
    if len(parts) >= 5 and all(p.isdigit() for p in parts[-3:]):
        out["cargo"] = _humanize_token(parts[0])
        out["nome"] = _humanize_token(parts[-4])
        out["data"] = "-".join(parts[-3:])
        cnh_guess = parts[1] if len(parts) >= 2 else None
        out["cnh"] = _normalize_cnh(cnh_guess)
        return out

    if len(parts) >= 2:
        out["cargo"] = _humanize_token(parts[0])
        out["nome"] = _humanize_token(parts[-1])
    return out


def build_resume_filename(
    *,
    cargo: str | None,
    cnh: str | None,
    nome: str | None,
    data_str: str | None,
    ext: str,
) -> str:
    safe_cargo = _slug_token(cargo or "sem_cargo")
    safe_cnh = _slug_token(_normalize_cnh(cnh) or "semcnh")
    if not safe_cnh.startswith("cnh_"):
        safe_cnh = f"cnh_{safe_cnh}"
    safe_nome = _slug_token(nome or "sem_nome")
    safe_data = _normalize_date_str(data_str) or datetime.utcnow().strftime("%d-%m-%Y")
    safe_ext = ext if ext.startswith(".") else f".{ext}"
    return f"{safe_cargo}-{safe_cnh}-{safe_nome}-{safe_data}{safe_ext.lower()}"


def _normalize_cnh(raw: str | None) -> str | None:
    if not raw:
        return None
    s = _norm(raw)
    s = s.replace("categoria", "").replace("cnh", "").replace("_", "").replace("-", "").strip()
    if not s:
        return None
    if len(s) == 1 and s in {"a", "b", "c", "d", "e"}:
        return s.upper()
    if s in {"semcnh", "sem_cnh", "nao", "none"}:
        return "SemCNH"
    return s.upper()


def _normalize_date_str(raw: str | None) -> str | None:
    if not raw:
        return None
    m = re.match(r"^\d{2}-\d{2}-\d{4}$", raw.strip())
    if m:
        return raw.strip()
    return None


def _humanize_token(value: str | None) -> str | None:
    if not value:
        return None
    v = value.replace("_", " ").strip(" -")
    return re.sub(r"\s+", " ", v).strip() or None


def _slug_token(value: str) -> str:
    norm = _norm(value)
    norm = norm.replace("/", " ").replace("-", " ").replace(".", " ")
    norm = re.sub(r"[^a-z0-9 ]+", " ", norm)
    norm = re.sub(r"\s+", "_", norm).strip("_")
    return norm or "na"


def _norm(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    return raw
