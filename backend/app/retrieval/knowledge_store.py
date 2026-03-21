"""本地知识库检索"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class KnowledgeStore:
    """基于本地JSON文件的知识检索器。"""

    def __init__(self, knowledge_path: str):
        self.knowledge_path = self._resolve_path(knowledge_path)
        self.items = self._load_items()

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not query.strip() or not self.items:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: list[dict[str, Any]] = []
        for item in self.items:
            score = self._score_item(item, query_tokens)
            if score <= 0:
                continue
            result = dict(item)
            result["score"] = round(score, 4)
            scored.append(result)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: max(1, top_k)]

    def _resolve_path(self, knowledge_path: str) -> Path:
        path = Path(knowledge_path)
        if path.is_absolute():
            return path
        app_dir = Path(__file__).resolve().parent.parent
        return app_dir / knowledge_path

    def _load_items(self) -> list[dict[str, Any]]:
        if not self.knowledge_path.exists():
            return []
        try:
            data = json.loads(self.knowledge_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            return []
        except Exception:
            return []

    def _score_item(self, item: dict[str, Any], query_tokens: set[str]) -> float:
        content_tokens = self._tokenize(
            " ".join(
                [
                    str(item.get("title", "")),
                    str(item.get("content", "")),
                    " ".join(item.get("tags", [])),
                ]
            )
        )
        if not content_tokens:
            return 0.0

        overlap = len(query_tokens.intersection(content_tokens))
        overlap_ratio = overlap / max(len(query_tokens), 1)
        confidence = float(item.get("confidence", 0.6))
        return overlap_ratio * 0.8 + confidence * 0.2

    def _tokenize(self, text: str) -> set[str]:
        text = text.lower()
        tokens = re.findall(r"[\u4e00-\u9fff]{1,}|[a-z0-9_]+", text)
        return {tok.strip() for tok in tokens if tok.strip()}
