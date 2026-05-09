from __future__ import annotations

from typing import Any, Protocol

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI


class LLMJudgePort(Protocol):
    async def complete(self, user_message: str) -> str: ...


class AnthropicJudgeAdapter:
    def __init__(self, client: AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, user_message: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=256,
            messages=[{"role": "user", "content": user_message}],
        )
        if response.content:
            block = response.content[0]
            return getattr(block, "text", "") or ""
        return ""


class OpenAICompatibleJudgeAdapter:
    """OpenAI API or any OpenAI-compatible API (e.g. DeepSeek)."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, user_message: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=256,
            messages=[{"role": "user", "content": user_message}],
        )
        choice = response.choices[0]
        content = choice.message.content
        return (content or "").strip()


DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}

DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com"


def build_llm_judge_adapter(settings: Any) -> LLMJudgePort | None:
    """Return a judge adapter, or None if no credentials for the chosen provider."""
    provider = (getattr(settings, "llm_judge_provider", "openai") or "openai").strip().lower()
    model = (getattr(settings, "llm_judge_model", "") or "").strip()
    anthropic_key = getattr(settings, "anthropic_api_key", "") or ""
    openai_key = getattr(settings, "openai_api_key", "") or ""
    openai_base_url = getattr(settings, "openai_base_url", None)

    if provider == "anthropic":
        if not anthropic_key:
            return None
        m = model or DEFAULT_MODELS["anthropic"]
        client = AsyncAnthropic(api_key=anthropic_key)
        return AnthropicJudgeAdapter(client, m)

    if provider == "openai":
        if not openai_key:
            return None
        base_url = openai_base_url
        m = model or DEFAULT_MODELS["openai"]
        kwargs: dict[str, Any] = {"api_key": openai_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)
        return OpenAICompatibleJudgeAdapter(client, m)

    if provider == "deepseek":
        if not openai_key:
            return None
        base_url = openai_base_url or DEEPSEEK_DEFAULT_BASE
        m = model or DEFAULT_MODELS["deepseek"]
        kwargs: dict[str, Any] = {"api_key": openai_key, "base_url": base_url}
        client = AsyncOpenAI(**kwargs)
        return OpenAICompatibleJudgeAdapter(client, m)

    return None
