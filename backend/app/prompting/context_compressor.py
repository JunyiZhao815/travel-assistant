"""上下文压缩模块"""

from __future__ import annotations

import json
from typing import Any

from ..models.schemas import ConversationTurn
from ..services.llm_service import get_llm


class ContextCompressor:
    """将长对话压缩为结构化摘要 + 最近轮次原文。"""

    def __init__(self, recent_turns: int = 4, summary_trigger_turns: int = 6):
        self.recent_turns = max(1, recent_turns)
        self.summary_trigger_turns = max(1, summary_trigger_turns)
        self.llm = get_llm()

    def build_context(self, history: list[ConversationTurn]) -> dict[str, Any]:
        """
        构造可直接注入提示词的上下文结构。

        Returns:
            {
              "summary": {...},
              "recent_turns": [{"role": "...", "content": "..."}]
            }
        """
        if not history:
            return {"summary": self._empty_summary(), "recent_turns": []}

        recent = history[-self.recent_turns :]
        if len(history) < self.summary_trigger_turns:
            return {
                "summary": self._rule_summary(history),
                "recent_turns": [t.model_dump() for t in recent],
            }

        summary = self._llm_summary(history)
        if not summary:
            summary = self._rule_summary(history)

        return {
            "summary": summary,
            "recent_turns": [t.model_dump() for t in recent],
        }

    def _llm_summary(self, history: list[ConversationTurn]) -> dict[str, Any] | None:
        lines = [f"{t.role}: {t.content}" for t in history]
        prompt = (
            "请把下面对话压缩为结构化JSON，且只返回JSON对象，不要额外文本。\n"
            "字段必须包含：user_goal, constraints, confirmed_preferences, open_questions, recent_changes。\n"
            "其中 constraints/confirmed_preferences/open_questions/recent_changes 必须是字符串数组。\n\n"
            "对话内容：\n"
            + "\n".join(lines)
        )
        response = self.llm.invoke(
            [
                {"role": "system", "content": "你是一个严格输出JSON的上下文压缩器。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=400,
        )
        return self._extract_json(response)

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        try:
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "{" in text and "}" in text:
                text = text[text.find("{") : text.rfind("}") + 1]
            data = json.loads(text)
            return self._normalize_summary(data)
        except Exception:
            return None

    def _rule_summary(self, history: list[ConversationTurn]) -> dict[str, Any]:
        user_text = " ".join([t.content for t in history if t.role == "user"])
        return {
            "user_goal": user_text[-120:] if user_text else "",
            "constraints": [],
            "confirmed_preferences": [],
            "open_questions": [],
            "recent_changes": [],
        }

    def _normalize_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        normalized = self._empty_summary()
        for key in normalized:
            value = data.get(key, normalized[key])
            if key == "user_goal":
                normalized[key] = str(value) if value else ""
            else:
                if isinstance(value, list):
                    normalized[key] = [str(x) for x in value if str(x).strip()]
                elif value:
                    normalized[key] = [str(value)]
        return normalized

    def _empty_summary(self) -> dict[str, Any]:
        return {
            "user_goal": "",
            "constraints": [],
            "confirmed_preferences": [],
            "open_questions": [],
            "recent_changes": [],
        }
