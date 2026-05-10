from __future__ import annotations

from chirp_sdk.wrap import wrap


async def check(agent_fn, input_payload: dict) -> dict:
    """
    Run a single agent invocation and return the Chirp wire-format dict
    (``output``, ``usage``, ``tool_calls``, optional extras) that HTTP agents
    should return to the Chirp runner.
    """
    return await wrap(agent_fn)(input_payload)
