from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json

from fastapi import Depends, Header, HTTPException, Request

from app.core.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="API key inválida")


RequireApiKey = Depends(require_api_key)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _sign(data: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def create_access_token(*, username: str, role: str) -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=max(15, int(settings.auth_token_ttl_minutes)))
    payload = {
        "sub": username,
        "role": (role or "viewer").strip().lower(),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_encoded = _b64url_encode(payload_json.encode("utf-8"))
    signature = _sign(payload_encoded, settings.auth_secret or settings.api_key or "fallback-secret")
    token = f"{payload_encoded}.{signature}"
    return {"access_token": token, "expires_at": exp.isoformat()}


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    raw = (token or "").strip()
    if not raw or "." not in raw:
        return None
    payload_part, signature_part = raw.split(".", 1)
    expected = _sign(payload_part, settings.auth_secret or settings.api_key or "fallback-secret")
    if not hmac.compare_digest(signature_part, expected):
        return None
    try:
        payload_bytes = _b64url_decode(payload_part)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int):
        return None
    if datetime.now(timezone.utc).timestamp() > exp:
        return None
    return payload


def _extract_token_from_request(*, authorization: str | None, request: Request | None) -> str | None:
    if isinstance(authorization, str) and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    settings = get_settings()
    if request is not None:
        cookie_token = request.cookies.get(settings.auth_cookie_name)
        if cookie_token:
            return cookie_token.strip()
    return None


def authenticate_credentials(*, username: str, password: str) -> dict | None:
    settings = get_settings()
    if (username or "").strip() != (settings.auth_username or "").strip():
        return None
    if (password or "") != (settings.auth_password or ""):
        return None
    role = (settings.auth_role or "admin").strip().lower()
    if role not in {"viewer", "recruiter", "manager", "admin"}:
        role = "admin"
    return {"username": settings.auth_username, "role": role}


def current_role(
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    request: Request = None,
) -> str:
    token_role = None
    token = _extract_token_from_request(authorization=authorization, request=request)
    if token:
        payload = decode_access_token(token)
        if payload:
            candidate = str(payload.get("role") or "").strip().lower()
            if candidate in {"viewer", "recruiter", "manager", "admin"}:
                token_role = candidate
    if token_role:
        return token_role
    role = (x_user_role or "viewer").strip().lower()
    if role not in {"viewer", "recruiter", "manager", "admin"}:
        role = "viewer"
    return role


def require_api_or_token(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    settings = get_settings()
    token = _extract_token_from_request(authorization=authorization, request=request)
    if token:
        payload = decode_access_token(token)
        if payload:
            return
    if not settings.api_key:
        return
    if x_api_key == settings.api_key:
        return
    raise HTTPException(status_code=401, detail="Não autenticado")


RequireApiOrToken = Depends(require_api_or_token)


def require_roles(*allowed_roles: str) -> Callable:
    normalized = {r.strip().lower() for r in allowed_roles if r}

    def _dep(role: str = Depends(current_role)) -> str:
        if normalized and role not in normalized:
            raise HTTPException(status_code=403, detail="Perfil sem permissão para esta ação.")
        return role

    return _dep
