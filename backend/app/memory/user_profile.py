"""长期用户画像服务"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class UserProfileRecord:
    """用户画像记录"""
    user_id: str
    preference_counts: dict[str, int] = field(default_factory=dict)
    city_counts: dict[str, int] = field(default_factory=dict)
    transportation_counts: dict[str, int] = field(default_factory=dict)
    accommodation_counts: dict[str, int] = field(default_factory=dict)
    travel_days_total: int = 0
    plan_count: int = 0
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_profile(self) -> dict[str, Any]:
        avg_days = round(self.travel_days_total / self.plan_count, 2) if self.plan_count else 0
        return {
            "user_id": self.user_id,
            "top_preferences": _top_items(self.preference_counts, 5),
            "top_cities": _top_items(self.city_counts, 5),
            "preferred_transportation": _top_one(self.transportation_counts),
            "preferred_accommodation": _top_one(self.accommodation_counts),
            "avg_travel_days": avg_days,
            "plan_count": self.plan_count,
            "updated_at": self.updated_at.isoformat(),
        }


def _top_items(counter: dict[str, int], k: int) -> list[str]:
    return [x[0] for x in sorted(counter.items(), key=lambda p: p[1], reverse=True)[:k]]


def _top_one(counter: dict[str, int]) -> str:
    return _top_items(counter, 1)[0] if counter else ""


class UserProfileService:
    """进程内长期用户画像服务（MVP）。"""

    def __init__(self):
        self._store: dict[str, UserProfileRecord] = {}
        self._lock = threading.Lock()

    def load(self, user_id: str) -> dict[str, Any]:
        if not user_id:
            return {}
        with self._lock:
            rec = self._store.get(user_id)
            return rec.to_profile() if rec else {}

    def update(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        if not user_id:
            return {}
        with self._lock:
            rec = self._store.get(user_id)
            if not rec:
                rec = UserProfileRecord(user_id=user_id)
                self._store[user_id] = rec

            for pref in patch.get("preferences", []) or []:
                _inc(rec.preference_counts, str(pref))
            _inc(rec.city_counts, patch.get("city", ""))
            _inc(rec.transportation_counts, patch.get("transportation", ""))
            _inc(rec.accommodation_counts, patch.get("accommodation", ""))

            travel_days = patch.get("travel_days")
            if isinstance(travel_days, int) and travel_days > 0:
                rec.travel_days_total += travel_days

            rec.plan_count += 1
            rec.updated_at = datetime.utcnow()
            return rec.to_profile()


def _inc(counter: dict[str, int], key: str) -> None:
    key = (key or "").strip()
    if not key:
        return
    counter[key] = counter.get(key, 0) + 1


_user_profile_service: UserProfileService | None = None


def get_user_profile_service() -> UserProfileService:
    global _user_profile_service
    if _user_profile_service is None:
        _user_profile_service = UserProfileService()
    return _user_profile_service
