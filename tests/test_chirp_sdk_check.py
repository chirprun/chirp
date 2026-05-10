import pytest

from chirp_sdk import check


@pytest.mark.asyncio
async def test_check_delegates_to_wrap():
    async def agent(_payload):
        return "done"

    out = await check(agent, {"task": "t"})
    assert out["output"] == "done"
    assert out["usage"]["input_tokens"] == 0
