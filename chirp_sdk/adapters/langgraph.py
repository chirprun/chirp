from __future__ import annotations

from typing import Any

from chirp_sdk.wrap import normalize_agent_result


def wrap_langgraph(graph: Any, *, input_key: str = "messages") -> Any:
    """Return an async handler that invokes ``graph.ainvoke`` / ``invoke`` with Chirp-shaped I/O."""

    async def wrapped(input_payload: dict) -> dict:
        state = {input_key: input_payload}
        ainvoke = getattr(graph, "ainvoke", None)
        if callable(ainvoke):
            raw = await ainvoke(state)
        else:
            invoke = getattr(graph, "invoke", None)
            if not callable(invoke):
                raise TypeError("graph must provide ainvoke or invoke")
            raw = invoke(state)
        return normalize_agent_result(raw)

    return wrapped
