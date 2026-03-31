from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _build_key() -> bytes:
    raw = (get_settings().pii_encryption_key or "").strip()
    if not raw:
        raw = "default-dev-insecure-key-change-me"
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    data = str(value).encode("utf-8")
    token = Fernet(_build_key()).encrypt(data)
    return token.decode("utf-8")


def decrypt_text(value: str | None) -> str | None:
    if not value:
        return None
    raw = Fernet(_build_key()).decrypt(value.encode("utf-8"))
    return raw.decode("utf-8")
