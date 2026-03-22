"""知识过期策略"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


class ExpirationPolicy:
    """按 valid_from/valid_to/ttl_days 进行知识有效性判定。"""

    def __init__(self, enabled: bool = True, default_ttl_days: int = 30):
        self.enabled = enabled
        self.default_ttl_days = max(1, default_ttl_days)

    def is_active(self, item: dict[str, Any], now: datetime | None = None) -> bool:
        if not self.enabled:
            return True
        now = now or datetime.utcnow()

        valid_from = self._parse_date(item.get("valid_from"))
        valid_to = self._parse_date(item.get("valid_to"))
        timestamp = self._parse_date(item.get("timestamp"))
        ttl_days = item.get("ttl_days")
        time_sensitive = bool(item.get("time_sensitive", False))

        if valid_from and now.date() < valid_from:
            return False
        if valid_to and now.date() > valid_to:
            return False

        if isinstance(ttl_days, int) and ttl_days > 0 and timestamp:
            expires_at = timestamp + timedelta(days=ttl_days)
            if now.date() > expires_at:
                return False

        if time_sensitive and not valid_to and not isinstance(ttl_days, int):
            # 时效知识但未显式配置有效期时，使用默认TTL兜底
            base = timestamp or now.date()
            expires_at = base + timedelta(days=self.default_ttl_days)
            if now.date() > expires_at:
                return False

        return True

    def annotate(self, item: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        enriched = dict(item)
        active = self.is_active(item, now=now)
        enriched["is_active"] = active
        enriched["expired"] = not active
        return enriched

    def _parse_date(self, value: Any) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except Exception:
            return None
