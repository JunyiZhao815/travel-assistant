"""RAG注入器"""

from __future__ import annotations

from typing import Any

from ..models.schemas import TripRequest
from .knowledge_store import KnowledgeStore


class RAGInjector:
    """检索知识并格式化为可注入Prompt的文本块。"""

    def __init__(self, knowledge_path: str, top_k: int = 3):
        self.store = KnowledgeStore(knowledge_path=knowledge_path)
        self.top_k = max(1, top_k)

    def retrieve(self, request: TripRequest, compressed_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query = self._build_query(request, compressed_context)
        return self.store.search(query=query, top_k=self.top_k)

    def build_prompt_block(self, retrieved_items: list[dict[str, Any]]) -> str:
        if not retrieved_items:
            return ""

        lines = ["**RAG知识片段(按相关度和可信度排序):**"]
        for idx, item in enumerate(retrieved_items, start=1):
            title = item.get("title", "未命名知识")
            content = item.get("content", "")
            source = item.get("source", "unknown")
            version = item.get("version", "v1")
            timestamp = item.get("timestamp", "")
            score = item.get("score", 0)
            lines.append(
                f"{idx}. {title}\n"
                f"   - content: {content}\n"
                f"   - source: {source}\n"
                f"   - version: {version}\n"
                f"   - timestamp: {timestamp}\n"
                f"   - score: {score}"
            )
        lines.append("请优先参考以上知识片段；若知识不足请明确说明不确定，不要编造事实。")
        return "\n".join(lines)

    def _build_query(self, request: TripRequest, compressed_context: dict[str, Any] | None = None) -> str:
        parts: list[str] = [
            request.city,
            request.transportation,
            request.accommodation,
            " ".join(request.preferences),
            request.free_text_input or "",
        ]
        if compressed_context:
            summary = compressed_context.get("summary", {})
            parts.append(summary.get("user_goal", ""))
            parts.extend(summary.get("constraints", []))
            parts.extend(summary.get("confirmed_preferences", []))
        return " ".join([x for x in parts if x]).strip()
