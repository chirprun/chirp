import pytest

from backend.engine.assertions import (
    evaluate_contains,
    evaluate_cost,
    evaluate_latency,
    evaluate_llm_judge,
    evaluate_tool_sequence,
)


def test_evaluate_latency_pass_fail_and_edge():
    assert evaluate_latency(2500, 3000).passed is True
    assert evaluate_latency(3500, 3000).passed is False
    assert evaluate_latency(0, 3000).passed is True


def test_evaluate_cost_pass_fail_and_edge():
    assert evaluate_cost(100, 200, 0.01).passed is True
    assert evaluate_cost(4500, 2800, 0.05).passed is False
    assert evaluate_cost(0, 0, 0.01).passed is True


def test_evaluate_contains_pass_fail_and_case_insensitive():
    assert evaluate_contains("hello world", "world").passed is True
    assert evaluate_contains("hello world", "xyz").passed is False
    assert evaluate_contains("Hello World", "world").passed is True


def test_evaluate_tool_sequence_cases():
    assert (
        evaluate_tool_sequence(["search", "format", "respond"], ["search", "respond"]).passed
        is True
    )
    assert evaluate_tool_sequence(["search", "respond"], ["respond", "search"]).passed is False
    assert evaluate_tool_sequence([], []).passed is True
    assert evaluate_tool_sequence(["search"], []).passed is True
    assert evaluate_tool_sequence([], ["search"]).passed is False


class _MockRespContent:
    def __init__(self, text: str):
        self.text = text


class _MockResp:
    def __init__(self, text: str):
        self.content = [_MockRespContent(text)]


class _MessagesAPI:
    def __init__(self, text: str):
        self._text = text

    async def create(self, **_kwargs):
        return _MockResp(self._text)


class _MockAnthropic:
    def __init__(self, text: str):
        self.messages = _MessagesAPI(text)


@pytest.mark.asyncio
async def test_evaluate_llm_judge_pass():
    client = _MockAnthropic('{"passed": true, "reason": "good", "confidence": 0.9}')
    result = await evaluate_llm_judge("output", "rubric", client)
    assert result.passed is True
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_evaluate_llm_judge_fail():
    client = _MockAnthropic('{"passed": false, "reason": "bad", "confidence": 0.6}')
    result = await evaluate_llm_judge("output", "rubric", client)
    assert result.passed is False
    assert result.confidence == 0.6


@pytest.mark.asyncio
async def test_evaluate_llm_judge_parse_error_defaults():
    client = _MockAnthropic("not-json")
    result = await evaluate_llm_judge("output", "rubric", client)
    assert result.passed is False
    assert result.confidence == 0.5
