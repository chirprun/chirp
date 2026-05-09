from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

PROMPT_TOKEN_RATE = 0.000003
RESPONSE_TOKEN_RATE = 0.000015


@dataclass(slots=True)
class AssertionOutcome:
    assertion_type: str
    passed: bool
    expected: str
    actual: str
    detail: str
    confidence: float | None = None


def evaluate_latency(actual_ms: int, threshold_ms: int) -> AssertionOutcome:
    passed = actual_ms < threshold_ms
    return AssertionOutcome(
        assertion_type="latency_ms",
        passed=passed,
        expected=f"latency < {threshold_ms}ms",
        actual=f"{actual_ms}ms",
        detail=f"Observed latency {actual_ms}ms against threshold {threshold_ms}ms",
    )


def evaluate_cost(input_tokens: int, output_tokens: int, threshold_usd: float) -> AssertionOutcome:
    prompt_cost = max(input_tokens, 0) * PROMPT_TOKEN_RATE
    response_cost = max(output_tokens, 0) * RESPONSE_TOKEN_RATE
    total_cost = prompt_cost + response_cost
    passed = total_cost < threshold_usd
    return AssertionOutcome(
        assertion_type="cost_usd",
        passed=passed,
        expected=f"cost < ${threshold_usd:.6f}",
        actual=f"${total_cost:.6f}",
        detail=(
            f"prompt_cost=${prompt_cost:.6f}, response_cost=${response_cost:.6f}, "
            f"total_cost=${total_cost:.6f}"
        ),
    )


def evaluate_contains(text: str, keyword: str) -> AssertionOutcome:
    normalized_text = (text or "").lower()
    normalized_keyword = (keyword or "").lower()
    passed = normalized_keyword in normalized_text
    return AssertionOutcome(
        assertion_type="output_contains",
        passed=passed,
        expected=f"contains '{keyword}'",
        actual=text or "",
        detail=f"Keyword '{keyword}' {'found' if passed else 'not found'} in output",
    )


def evaluate_tool_sequence(actual_calls: list[str], expected_sequence: list[str]) -> AssertionOutcome:
    actual = actual_calls or []
    expected = expected_sequence or []
    if not expected:
        return AssertionOutcome(
            assertion_type="tool_call_sequence",
            passed=True,
            expected="any sequence",
            actual=str(actual),
            detail="No expected tool sequence configured",
        )

    pointer = 0
    for call in actual:
        if pointer < len(expected) and call == expected[pointer]:
            pointer += 1

    passed = pointer == len(expected)
    return AssertionOutcome(
        assertion_type="tool_call_sequence",
        passed=passed,
        expected=str(expected),
        actual=str(actual),
        detail=(
            "Expected sequence matched as subsequence"
            if passed
            else "Expected sequence not found as ordered subsequence"
        ),
    )


async def evaluate_llm_judge(output_text: str, rubric: str, judge) -> AssertionOutcome:
    if judge is None:
        return AssertionOutcome(
            assertion_type="llm_judge",
            passed=False,
            expected=f"rubric: {rubric}",
            actual=output_text or "",
            detail="LLM judge not configured (set API keys and LLM_JUDGE_PROVIDER, or DEMO_MODE with demo cache)",
            confidence=0.5,
        )

    prompt = (
        "You are an evaluator. Assess whether this agent response meets the rubric. "
        'Return ONLY valid JSON: {"passed": true/false, "reason": "...", "confidence": 0.0-1.0}. '
        "No markdown, no explanation outside the JSON. "
        f"Rubric: {rubric}. Agent response: {output_text}"
    )
    try:
        raw_text = await asyncio.wait_for(judge.complete(prompt), timeout=10)
    except TimeoutError:
        return AssertionOutcome(
            assertion_type="llm_judge",
            passed=False,
            expected=f"rubric: {rubric}",
            actual="timeout",
            detail="Judge timeout",
            confidence=0.5,
        )
    except Exception as exc:  # pragma: no cover - exercised in runner paths
        return AssertionOutcome(
            assertion_type="llm_judge",
            passed=False,
            expected=f"rubric: {rubric}",
            actual=str(exc),
            detail=f"Judge call error: {exc}",
            confidence=0.5,
        )
    try:
        parsed = json.loads(raw_text)
        passed = bool(parsed.get("passed", False))
        reason = str(parsed.get("reason", "No reason provided"))
        confidence = float(parsed.get("confidence", 0.5))
        return AssertionOutcome(
            assertion_type="llm_judge",
            passed=passed,
            expected=f"rubric: {rubric}",
            actual=output_text or "",
            detail=reason,
            confidence=confidence,
        )
    except Exception:
        return AssertionOutcome(
            assertion_type="llm_judge",
            passed=False,
            expected=f"rubric: {rubric}",
            actual=raw_text,
            detail="Judge parse error",
            confidence=0.5,
        )
