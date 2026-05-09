from __future__ import annotations


def wrap(agent_fn):
    async def wrapped(input_payload: dict) -> dict:
        result = await agent_fn(input_payload)

        if isinstance(result, str):
            return {
                "output": result,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "tool_calls": [],
            }

        return {
            "output": result.get("output") or result.get("text") or result.get("content") or str(result),
            "usage": result.get("usage") or result.get("tokens") or {"input_tokens": 0, "output_tokens": 0},
            "tool_calls": result.get("tool_calls") or result.get("actions") or result.get("tools_used") or [],
        }

    return wrapped
