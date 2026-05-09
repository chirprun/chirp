import pytest

from chirp_sdk.wrap import wrap


@pytest.mark.asyncio
async def test_wrap_normalizes_string_result():
    async def agent(_payload):
        return "ok"

    wrapped = wrap(agent)
    result = await wrapped({"task": "x"})
    assert result["output"] == "ok"
    assert result["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert result["tool_calls"] == []


@pytest.mark.asyncio
async def test_wrap_normalizes_dict_result():
    async def agent(_payload):
        return {"text": "ok", "tokens": {"input_tokens": 1, "output_tokens": 2}, "actions": ["search"]}

    wrapped = wrap(agent)
    result = await wrapped({"task": "x"})
    assert result["output"] == "ok"
    assert result["usage"] == {"input_tokens": 1, "output_tokens": 2}
    assert result["tool_calls"] == ["search"]
