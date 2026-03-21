"""冲突指令消解模块"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Instruction:
    """单条指令"""
    text: str
    layer: str
    priority: int
    category: str


class InstructionResolver:
    """
    指令优先级:
    system(4) > developer(3) > user(2) > retrieved(1)
    """

    LAYER_PRIORITY = {
        "system": 4,
        "developer": 3,
        "user": 2,
        "retrieved": 1,
    }

    def resolve(
        self,
        system_rules: list[str],
        developer_rules: list[str],
        user_rules: list[str],
        retrieved_rules: list[str],
    ) -> dict[str, Any]:
        instructions = self._collect(system_rules, developer_rules, user_rules, retrieved_rules)
        chosen: dict[str, Instruction] = {}
        conflicts: list[dict[str, str]] = []

        for item in instructions:
            if self._is_override_attempt(item):
                conflicts.append(
                    {
                        "layer": item.layer,
                        "directive": item.text,
                        "reason": "detected_override_attempt",
                    }
                )
                continue

            current = chosen.get(item.category)
            if not current:
                chosen[item.category] = item
                continue

            if item.priority > current.priority:
                conflicts.append(
                    {
                        "layer": current.layer,
                        "directive": current.text,
                        "reason": f"overridden_by_{item.layer}",
                    }
                )
                chosen[item.category] = item
            elif item.priority < current.priority and item.text.strip() != current.text.strip():
                conflicts.append(
                    {
                        "layer": item.layer,
                        "directive": item.text,
                        "reason": f"lower_priority_than_{current.layer}",
                    }
                )
            else:
                if item.text.strip() != current.text.strip():
                    conflicts.append(
                        {
                            "layer": item.layer,
                            "directive": item.text,
                            "reason": "same_priority_conflict_keep_first",
                        }
                    )

        effective = [x.text for x in sorted(chosen.values(), key=lambda i: i.priority, reverse=True)]
        return {
            "effective_rules": effective,
            "conflicts": conflicts,
        }

    def _collect(
        self,
        system_rules: list[str],
        developer_rules: list[str],
        user_rules: list[str],
        retrieved_rules: list[str],
    ) -> list[Instruction]:
        output: list[Instruction] = []
        for layer, rules in [
            ("system", system_rules),
            ("developer", developer_rules),
            ("user", user_rules),
            ("retrieved", retrieved_rules),
        ]:
            for text in rules:
                text = text.strip()
                if not text:
                    continue
                output.append(
                    Instruction(
                        text=text,
                        layer=layer,
                        priority=self.LAYER_PRIORITY[layer],
                        category=self._classify(text),
                    )
                )
        return output

    def _classify(self, text: str) -> str:
        t = text.lower()
        if "json" in t or "格式" in t:
            return "output_format"
        if "预算" in t or "cost" in t or "费用" in t:
            return "budget"
        if "餐" in t or "breakfast" in t or "lunch" in t or "dinner" in t:
            return "meal"
        if "天气" in t or "weather" in t:
            return "weather"
        if "工具" in t or "tool" in t:
            return "tool_usage"
        if "编造" in t or "不确定" in t or "真实" in t:
            return "truthfulness"
        if "交通" in t or "route" in t:
            return "transport"
        return "general"

    def _is_override_attempt(self, item: Instruction) -> bool:
        if item.layer in {"system", "developer"}:
            return False
        patterns = [
            r"忽略.*系统",
            r"无视.*规则",
            r"不要遵循.*(system|系统|developer|开发)",
            r"覆盖.*指令",
            r"绕过.*限制",
        ]
        return any(re.search(p, item.text, re.IGNORECASE) for p in patterns)
