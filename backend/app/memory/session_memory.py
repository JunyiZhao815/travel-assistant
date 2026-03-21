"""短期会话记忆服务"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class SessionRecord:
    """单个会话记忆记录"""
    session_id: str
    slots: dict[str, Any] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))


class SessionMemoryService:
    """进程内短期会话记忆（MVP）。"""

    def __init__(self, ttl_minutes: int = 1440):
        self.ttl_minutes = max(1, ttl_minutes)
        self._store: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def load(self, session_id: str) -> dict[str, Any]:
        if not session_id:
            return {}
        with self._lock:
            self._purge_expired_locked()
            record = self._store.get(session_id)
            if not record:
                return {}
            return dict(record.slots)

    def update(self, session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        if not session_id:
            return {}
        with self._lock:
            self._purge_expired_locked()
            record = self._store.get(session_id)
            if not record:
                record = SessionRecord(session_id=session_id)
                self._store[session_id] = record

            for key, value in patch.items():
                if value in (None, "", []):
                    continue
                record.slots[key] = value

            record.last_updated = datetime.utcnow()
            record.expires_at = datetime.utcnow() + timedelta(minutes=self.ttl_minutes)
            return dict(record.slots)

    def _purge_expired_locked(self) -> None:
        now = datetime.utcnow()
        expired = [sid for sid, rec in self._store.items() if rec.expires_at <= now]
        for sid in expired:
            self._store.pop(sid, None)


_session_memory: SessionMemoryService | None = None


def get_session_memory_service(ttl_minutes: int = 1440) -> SessionMemoryService:
    global _session_memory
    if _session_memory is None:
        _session_memory = SessionMemoryService(ttl_minutes=ttl_minutes)
    return _session_memory
