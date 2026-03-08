"""LLM服务模块"""

from typing import Iterator

from openai import OpenAI

from ..config import get_settings


class HunyuanLLM:
    """兼容SimpleAgent接口的混元LLM封装。"""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url
        self.model = settings.openai_model
        self.provider = "hunyuan"

        if not self.api_key:
            raise ValueError("未配置固定的LLM API Key(settings.openai_api_key)")

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def invoke(self, messages: list[dict[str, str]], **kwargs) -> str:
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        extra_body = kwargs.get("extra_body", {"enable_enhancement": True})

        completion = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        content = completion.choices[0].message.content
        return content or ""

    def stream_invoke(self, messages: list[dict[str, str]], **kwargs) -> Iterator[str]:
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        extra_body = kwargs.get("extra_body", {"enable_enhancement": True})

        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
            stream=True,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def think(self, messages: list[dict[str, str]], temperature: float | None = None) -> Iterator[str]:
        yield from self.stream_invoke(messages, temperature=temperature)


# 全局LLM实例
_llm_instance = None


def get_llm() -> HunyuanLLM:
    """获取LLM实例(单例模式)"""
    global _llm_instance

    if _llm_instance is None:
        _llm_instance = HunyuanLLM()

        print("✅ LLM服务初始化成功")
        print(f"   提供商: {_llm_instance.provider}")
        print(f"   模型: {_llm_instance.model}")
        print(f"   Base URL: {_llm_instance.base_url}")

    return _llm_instance


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None
