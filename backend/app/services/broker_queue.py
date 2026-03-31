from __future__ import annotations

import json

from app.core.config import get_settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


class BrokerQueue:
    def __init__(self):
        self.settings = get_settings()
        self._client = None
        url = getattr(self.settings, "broker_url", "") or ""
        if redis and url:
            try:
                self._client = redis.Redis.from_url(url, decode_responses=True)
            except Exception:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def publish(self, queue_name: str, payload: dict) -> bool:
        if not self._client:
            return False
        self._client.rpush(queue_name, json.dumps(payload, ensure_ascii=False))
        return True

    def consume(self, queue_name: str, timeout_seconds: int = 1) -> dict | None:
        if not self._client:
            return None
        item = self._client.blpop(queue_name, timeout=timeout_seconds)
        if not item:
            return None
        _, raw = item
        try:
            return json.loads(raw)
        except Exception:
            return {"raw": raw}
