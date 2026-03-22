"""知识版本注册与选择"""

from __future__ import annotations

import re
from typing import Any


class KnowledgeRegistry:
    """
    负责知识版本治理:
    - 规范化 version metadata
    - 按 knowledge_key 选择最新版本
    """

    def __init__(self, enabled: bool = True, keep_latest_only: bool = True):
        self.enabled = enabled
        self.keep_latest_only = keep_latest_only

    def process(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = [self._normalize(x) for x in items]
        if not self.enabled or not self.keep_latest_only:
            return normalized
        return self._pick_latest(normalized)

    def _pick_latest(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best: dict[str, dict[str, Any]] = {}
        for item in items:
            key = str(item.get("knowledge_key") or item.get("id") or "")
            if not key:
                continue
            existing = best.get(key)
            if not existing:
                best[key] = item
                continue
            if self._version_rank(item.get("version", "")) > self._version_rank(existing.get("version", "")):
                best[key] = item
        return list(best.values())

    def _normalize(self, item: dict[str, Any]) -> dict[str, Any]:
        x = dict(item)
        x.setdefault("knowledge_key", x.get("id", ""))
        x.setdefault("version", "v1")
        x.setdefault("source", "unknown")
        x.setdefault("timestamp", "")
        return x

    def _version_rank(self, version: str) -> tuple[int, ...]:
        # 支持 "v1", "1.2.3", "2026.03.01" 等形式
        nums = re.findall(r"\d+", str(version))
        if not nums:
            return (0,)
        return tuple(int(x) for x in nums)
