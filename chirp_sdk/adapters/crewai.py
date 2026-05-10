from __future__ import annotations

from typing import Any

from chirp_sdk.wrap import normalize_agent_result


def _crew_usage(crew: Any) -> dict:
    usage = getattr(crew, "token_usage", None) or getattr(crew, "usage", None) or {}
    if isinstance(usage, dict):
        return {
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
        }
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    return {"input_tokens": inp, "output_tokens": out}


def wrap_crewai(crew: Any) -> Any:
    """Return an async handler for CrewAI-style crews (``kickoff_async`` / ``kickoff``)."""

    async def wrapped(input_payload: dict) -> dict:
        kick_async = getattr(crew, "kickoff_async", None)
        if callable(kick_async):
            result = await kick_async(inputs=input_payload)
        else:
            kick = getattr(crew, "kickoff", None)
            if not callable(kick):
                raise TypeError("crew must provide kickoff_async or kickoff")
            result = kick(inputs=input_payload)
        raw = getattr(result, "raw", None)
        if raw is None:
            raw = str(result)
        normalized = normalize_agent_result(raw if isinstance(raw, (str, dict)) else str(raw))
        normalized["usage"] = _crew_usage(result)
        return normalized

    return wrapped
