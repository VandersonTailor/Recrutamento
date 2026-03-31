import re

_CITY_NOISE_TERMS = (
    "capacidade",
    "habilidade",
    "habilidades",
    "motivacao",
    "objetivo",
    "aprendo",
    "equipe",
    "colegas",
    "proativo",
    "multitarefas",
    "resumo",
    "perfil",
    "experiencia",
)

_BR_UF_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

_BR_STATE_NAMES = {
    "acre",
    "alagoas",
    "amapa",
    "amazonas",
    "bahia",
    "ceara",
    "distrito federal",
    "espirito santo",
    "goias",
    "maranhao",
    "mato grosso",
    "mato grosso do sul",
    "minas gerais",
    "para",
    "paraiba",
    "parana",
    "pernambuco",
    "piaui",
    "rio de janeiro",
    "rio grande do norte",
    "rio grande do sul",
    "rondonia",
    "roraima",
    "santa catarina",
    "sao paulo",
    "sergipe",
    "tocantins",
}


def extract_email(text: str) -> str | None:
    text = _sanitize_text(text)
    if not text:
        return None
    m = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text, flags=re.IGNORECASE)
    if not m:
        return None
    email = m.group(0).strip().lower()
    if len(email) > 200:
        return None
    return email


def extract_phone(text: str) -> str | None:
    text = _sanitize_text(text)
    if not text:
        return None
    candidates = re.findall(
        r"(\+\d{1,3}\s*)?(\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}",
        text,
        flags=re.IGNORECASE,
    )
    if not candidates:
        m = re.search(r"(\+\d{1,3}\s*)?(\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}", text)
        if not m:
            return None
        raw = m.group(0)
    else:
        m = re.search(r"(\+\d{1,3}\s*)?(\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}", text)
        raw = m.group(0) if m else None
        if not raw:
            return None

    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10:
        return None
    if len(digits) > 13:
        digits = digits[-13:]
    return digits


def extract_address(text: str) -> str | None:
    text = _sanitize_text(text)
    if not text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None

    keywords = (
        "rua",
        "avenida",
        "av.",
        "av ",
        "rodovia",
        "estrada",
        "travessa",
        "alameda",
        "bairro",
        "cep",
        "endereco",
        "endereço",
        "localizacao",
        "localização",
        "cidade:",
        "cidade ",
        "reside em",
    )
    for i, ln in enumerate(lines[:300]):
        low = ln.lower()
        if low.startswith("endereço:"):
            ln = ln.split(":", 1)[1].strip()
            low = ln.lower()
        if "(cid:" in ln:
            continue
        if any(k in low for k in keywords):
            parts = [ln]
            if i + 1 < len(lines) and len(lines[i + 1]) <= 80:
                nxt = lines[i + 1]
                if any(k in nxt.lower() for k in ("cep", "bairro", "cidade", "estado")) or re.search(r"\b\d{5}-?\d{3}\b", nxt):
                    parts.append(nxt)
            addr = " | ".join(parts).strip()
            if len(addr) >= 8:
                return addr[:500]

    # fallback: aceita localidade simples (cidade, estado/UF) se parecer endereço/localização
    for ln in lines[:200]:
        extracted = _extract_city_state_fragment(ln)
        if extracted:
            return extracted[:500]

    return None


def extract_linkedin(text: str) -> str | None:
    text = _sanitize_text(text)
    if not text:
        return None
    m = re.search(r"(https?://)?(www\.)?linkedin\.com/[A-Za-z0-9_\-/%\.\?=&]+", text, flags=re.IGNORECASE)
    if not m:
        return None
    url = m.group(0).strip().rstrip(").,;")
    if not url.lower().startswith("http"):
        url = "https://" + url.lstrip("/")
    if len(url) > 260:
        return None
    return url


def build_professional_summary(text: str) -> str | None:
    text = _sanitize_text(text)
    if not text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    blacklist = (
        "curriculum",
        "currículo",
        "cpf",
        "rg",
        "endereço",
        "telefone",
        "cep",
        "rua",
        "avenida",
        "linha digitável",
        "impressão",
        "instruções",
        "código de barras",
    )
    picked: list[str] = []
    seen = set()
    for ln in lines[:400]:
        low = ln.lower()
        if any(b in low for b in blacklist):
            continue
        if "@" in ln:
            continue
        if re.search(r"\b\d{2}\b/\b\d{2}\b/\b\d{4}\b", ln):
            continue
        if "(cid:" in ln:
            continue
        if len(re.sub(r"\W+", "", ln)) < 6:
            continue
        if 20 <= len(ln) <= 160:
            if ln not in seen:
                picked.append(ln)
                seen.add(ln)
        if len(picked) >= 6:
            break
    if not picked:
        picked = lines[:3]
    summary = "\n".join(picked).strip()
    return summary[:2000] if summary else None


def validate_contact(email: str | None, phone: str | None) -> list[str]:
    warnings: list[str] = []
    if not email:
        warnings.append("Email não encontrado no currículo.")
    if not phone:
        warnings.append("Telefone não encontrado no currículo.")
    return warnings


def is_address_plausible(address: str | None) -> bool:
    raw = _sanitize_text(address or "")
    if not raw:
        return False

    low = raw.lower()
    if "cid:" in low:
        return False

    address_keywords = (
        "rua",
        "avenida",
        "av.",
        "av ",
        "rodovia",
        "estrada",
        "travessa",
        "alameda",
        "bairro",
        "cep",
    )
    noisy_terms = (
        "trabalho em equipe",
        *list(_CITY_NOISE_TERMS),
    )

    if any(t in low for t in noisy_terms) and not any(k in low for k in address_keywords):
        return False

    has_keyword = any(k in low for k in address_keywords)
    has_number = bool(re.search(r"\b\d{1,5}\b", low))
    if has_keyword and (has_number or "bairro" in low or "cep" in low):
        return True

    # Cidade, Estado/UF (ex: Porto Alegre, Rio Grande do Sul | Porto Alegre/RS)
    if _extract_city_state_fragment(raw):
        return True

    return False


def _extract_city_state_fragment(line: str) -> str | None:
    if not line:
        return None
    txt = _sanitize_text(line)
    if not txt:
        return None

    patterns = [
        re.compile(r"([A-Za-zÀ-ÿ' ]{2,40})\s*,\s*([A-Za-zÀ-ÿ' ]{2,35}|[A-Z]{2})"),
        re.compile(r"([A-Za-zÀ-ÿ' ]{2,40})\s*/\s*([A-Z]{2})"),
    ]
    for pat in patterns:
        m = pat.search(txt)
        if not m:
            continue
        city = m.group(1).strip(" .,-")
        state = m.group(2).strip(" .,-").upper() if len(m.group(2).strip()) == 2 else m.group(2).strip(" .,-")
        if _is_valid_city_state(city, state):
            return f"{city}, {state}"
    return None


def _is_valid_city_state(city: str, state: str) -> bool:
    city_low = city.lower()
    if any(term in city_low for term in _CITY_NOISE_TERMS):
        return False
    if any(ch.isdigit() for ch in city):
        return False
    city_words = [w for w in city.split() if w]
    if not (1 <= len(city_words) <= 4):
        return False
    if len(city) > 40:
        return False

    state_norm = _norm_ascii(state)
    if len(state.strip()) == 2 and state.strip().upper() in _BR_UF_CODES:
        return True
    if state_norm in _BR_STATE_NAMES:
        return True
    return False


def _norm_ascii(value: str) -> str:
    s = _sanitize_text(value).lower()
    s = (
        s.replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("ã", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _sanitize_text(text: str) -> str:
    if not text:
        return text
    s = text
    s = s.replace("\u00A0", " ")
    s = re.sub(r"\(cid:[^)]+\)", " ", s)
    s = re.sub(r"[^\S\r\n]+", " ", s)
    s = re.sub(r"([A-Za-zÀ-ÿ])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)([A-Za-zÀ-ÿ])", r"\1 \2", s)
    s = re.sub(r"([a-zà-ÿ])([A-ZÀ-Ý])", r"\1 \2", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()
