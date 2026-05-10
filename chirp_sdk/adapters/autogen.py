from __future__ import annotations

from typing import Any

from chirp_sdk.wrap import normalize_agent_result


def wrap_autogen_chat(team_or_chat: Any, *, message_builder: Any | None = None) -> Any:
    """Wrap an AutoGen-style chat object with ``a_initiate_chat`` / ``initiate_chat``."""

    async def wrapped(input_payload: dict) -> dict:
        if message_builder is not None:
            message = await message_builder(input_payload) if callable(message_builder) else message_builder
        else:
            message = input_payload.get("task") or input_payload.get("message") or str(input_payload)

        a_chat = getattr(team_or_chat, "a_initiate_chat", None)
        if callable(a_chat):
            result = await a_chat(message=message)
        else:
            sync = getattr(team_or_chat, "initiate_chat", None)
            if not callable(sync):
                raise TypeError("team_or_chat must provide a_initiate_chat or initiate_chat")
            result = sync(message=message)

        summary = getattr(result, "summary", None)
        if summary is not None:
            text = str(summary)
        else:
            text = str(result)
        return normalize_agent_result(text)

    return wrapped
