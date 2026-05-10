from __future__ import annotations

import pytest

from chirp_sdk.adapters.autogen import wrap_autogen_chat
from chirp_sdk.adapters.crewai import wrap_crewai
from chirp_sdk.adapters.langgraph import wrap_langgraph


@pytest.mark.asyncio
async def test_wrap_langgraph_ainvoke():
    class _Graph:
        async def ainvoke(self, state):
            return {"output": "done", "usage": {"input_tokens": 1, "output_tokens": 2}, "tool_calls": []}

    fn = wrap_langgraph(_Graph(), input_key="messages")
    out = await fn({"task": "x"})
    assert out["output"] == "done"
    assert out["usage"]["input_tokens"] == 1


@pytest.mark.asyncio
async def test_wrap_langgraph_invoke_sync():
    class _Graph:
        def invoke(self, state):
            return "plain"

    fn = wrap_langgraph(_Graph(), input_key="x")
    out = await fn({"a": 1})
    assert out["output"] == "plain"


@pytest.mark.asyncio
async def test_wrap_crewai_kickoff_async():
    class _Result:
        raw = {"output": "crew-out", "usage": {"input_tokens": 3, "output_tokens": 4}}
        token_usage = {"input_tokens": 10, "output_tokens": 20}

    class _Crew:
        async def kickoff_async(self, inputs):
            return _Result()

    fn = wrap_crewai(_Crew())
    out = await fn({"task": "t"})
    assert out["output"] == "crew-out"
    assert out["usage"]["input_tokens"] == 10


@pytest.mark.asyncio
async def test_wrap_autogen_a_initiate_chat():
    class _ChatResult:
        summary = "autogen summary"

    class _Team:
        async def a_initiate_chat(self, message):
            assert message == "hello"
            return _ChatResult()

    fn = wrap_autogen_chat(_Team())
    out = await fn({"task": "hello"})
    assert out["output"] == "autogen summary"
