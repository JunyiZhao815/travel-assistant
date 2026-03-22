"""本地知识库检索"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..knowledge.expiration_policy import ExpirationPolicy
from ..knowledge.knowledge_registry import KnowledgeRegistry
from .pgvector_store import PgVectorStore
from .vector_store import VectorStore


class KnowledgeStore:
    """基于本地JSON文件的知识检索器。"""

    def __init__(
        self,
        knowledge_path: str,
        vector_backend: str = "local",
        pgvector_dsn: str = "",
        pgvector_table: str = "rag_knowledge_vectors",
        pgvector_dim: int = 256,
        versioning_enabled: bool = True,
        keep_latest_only: bool = True,
        expiration_enabled: bool = True,
        default_ttl_days: int = 30,
    ):
        self.knowledge_path = self._resolve_path(knowledge_path)
        raw_items = self._load_items()
        self.registry = KnowledgeRegistry(enabled=versioning_enabled, keep_latest_only=keep_latest_only)
        self.expiration_policy = ExpirationPolicy(
            enabled=expiration_enabled, default_ttl_days=default_ttl_days
        )
        versioned_items = self.registry.process(raw_items)
        self.items = [self.expiration_policy.annotate(x) for x in versioned_items]
        self.items = [x for x in self.items if x.get("is_active", True)]
        self.vector_backend = vector_backend
        self.vector_store = VectorStore(self.items, tokenize=self._tokenize_list) if self.items else None
        self.pgvector_store = None
        if self.items and self.vector_backend == "pgvector" and pgvector_dsn:
            self.pgvector_store = PgVectorStore(
                dsn=pgvector_dsn,
                table_name=pgvector_table,
                dim=pgvector_dim,
            )
            if self.pgvector_store.available:
                self.pgvector_store.sync_items(self.items)

    def search(
        self,
        query: str,
        top_k: int = 3,
        mode: str = "hybrid",
        keyword_weight: float = 0.4,
        vector_weight: float = 0.5,
        confidence_weight: float = 0.1,
    ) -> list[dict[str, Any]]:
        if not query.strip() or not self.items:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        vector_scores: dict[str, float] = {}
        if self.vector_store and mode in {"vector", "hybrid"}:
            if self.vector_backend == "pgvector" and self.pgvector_store and self.pgvector_store.available:
                for hit in self.pgvector_store.search(query=query, top_k=max(top_k * 3, top_k)):
                    vector_scores[str(hit["id"])] = float(hit["vector_score"])
            else:
                for hit in self.vector_store.search(query=query, top_k=max(top_k * 3, top_k)):
                    idx = int(hit["index"])
                    item_id = str(self.items[idx].get("id") or f"knowledge_{idx}")
                    vector_scores[item_id] = float(hit["vector_score"])

        scored: list[dict[str, Any]] = []
        for idx, item in enumerate(self.items):
            item_id = str(item.get("id") or f"knowledge_{idx}")
            keyword_score = self._keyword_score(item, query_tokens)
            vector_score = vector_scores.get(item_id, 0.0)
            confidence = float(item.get("confidence", 0.6))
            score = self._compose_score(
                mode=mode,
                keyword_score=keyword_score,
                vector_score=vector_score,
                confidence=confidence,
                keyword_weight=keyword_weight,
                vector_weight=vector_weight,
                confidence_weight=confidence_weight,
            )

            if score <= 0:
                continue
            result = dict(item)
            result["keyword_score"] = round(keyword_score, 4)
            result["vector_score"] = round(vector_score, 4)
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

    def _keyword_score(self, item: dict[str, Any], query_tokens: set[str]) -> float:
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
        return overlap / max(len(query_tokens), 1)

    def _compose_score(
        self,
        mode: str,
        keyword_score: float,
        vector_score: float,
        confidence: float,
        keyword_weight: float,
        vector_weight: float,
        confidence_weight: float,
    ) -> float:
        if mode == "keyword":
            return keyword_score * (1 - confidence_weight) + confidence * confidence_weight
        if mode == "vector":
            return vector_score * (1 - confidence_weight) + confidence * confidence_weight
        return (
            keyword_score * keyword_weight
            + vector_score * vector_weight
            + confidence * confidence_weight
        )

    def _tokenize(self, text: str) -> set[str]:
        text = text.lower()
        tokens = re.findall(r"[\u4e00-\u9fff]{1,}|[a-z0-9_]+", text)
        return {tok.strip() for tok in tokens if tok.strip()}

    def _tokenize_list(self, text: str) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"[\u4e00-\u9fff]{1,}|[a-z0-9_]+", text)
        return [tok.strip() for tok in tokens if tok.strip()]
