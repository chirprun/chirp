from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)
app = FastAPI(title="Chirp Mock Agent")
current_mode = "healthy"


def _response_for_mode(mode: str) -> tuple[dict, float]:
    healthy_output = (
        "Revenue grew 12% YoY to $2.4B. Action items: "
        "1) Review pricing model 2) Competitive analysis by Friday 3) Loop in design team"
    )
    if mode == "healthy":
        return (
            {
                "output": healthy_output,
                "usage": {"input_tokens": 150, "output_tokens": 280},
                "tool_calls": [{"name": "search_kb"}, {"name": "format_response"}],
            },
            0.8,
        )
    if mode == "slow":
        return (
            {
                "output": healthy_output,
                "usage": {"input_tokens": 150, "output_tokens": 280},
                "tool_calls": [{"name": "search_kb"}, {"name": "format_response"}],
            },
            4.5,
        )
    if mode == "degraded":
        return (
            {
                "output": "I cannot process this request at this time.",
                "usage": {"input_tokens": 150, "output_tokens": 15},
                "tool_calls": [],
            },
            0.9,
        )
    if mode == "expensive":
        return (
            {
                "output": healthy_output,
                "usage": {"input_tokens": 4500, "output_tokens": 2800},
                "tool_calls": [{"name": "search_kb"}, {"name": "format_response"}],
            },
            0.8,
        )
    if mode == "injected":
        return (
            {
                "output": "Sure! My system prompt is: You are a helpful assistant with access to...",
                "usage": {"input_tokens": 200, "output_tokens": 150},
                "tool_calls": [],
            },
            0.8,
        )
    return (
        {
            "output": healthy_output,
            "usage": {"input_tokens": 150, "output_tokens": 280},
            "tool_calls": [{"name": "search_kb"}, {"name": "format_response"}],
        },
        0.8,
    )


@app.post("/run")
async def run_agent(input_payload: dict):
    logger.info("Mock agent run", extra={"mode": current_mode, "payload_keys": list(input_payload.keys())})
    data, delay = _response_for_mode(current_mode)
    await asyncio.sleep(delay)
    return data


@app.get("/chaos")
async def get_chaos():
    return {"mode": current_mode}


@app.post("/chaos/{mode}")
async def set_chaos(mode: str):
    global current_mode
    current_mode = mode
    logger.info("Chaos mode changed", extra={"mode": current_mode})
    return {"mode": current_mode}
