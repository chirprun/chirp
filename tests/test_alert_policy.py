from datetime import datetime, timezone
from types import SimpleNamespace

from backend.engine.alert_policy import evaluate_alert_policy


def _run(status: str):
    return SimpleNamespace(status=status)


def _result(assertion_type: str, passed: bool, confidence: float | None):
    return SimpleNamespace(assertion_type=assertion_type, passed=passed, confidence=confidence)


def _policy(threshold: int = 2, confidence: float = 0.7):
    return SimpleNamespace(
        id="p1",
        scenario_id="s1",
        consecutive_failures_threshold=threshold,
        llm_judge_confidence_threshold=confidence,
        created_at=datetime.now(timezone.utc),
    )


def test_alert_threshold_behavior():
    policy = _policy(threshold=2, confidence=0.7)
    assert evaluate_alert_policy([_run("FAIL")], policy, [[]]).should_alert is False
    assert (
        evaluate_alert_policy(
            [_run("FAIL"), _run("FAIL")],
            policy,
            [[_result("llm_judge", False, 0.9)], [_result("llm_judge", False, 0.9)]],
        ).should_alert
        is True
    )
    assert (
        evaluate_alert_policy(
            [_run("ERROR"), _run("FAIL"), _run("FAIL")],
            policy,
            [[], [_result("llm_judge", False, 0.9)], [_result("llm_judge", False, 0.9)]],
        ).should_alert
        is True
    )


def test_confidence_filter_behavior():
    policy = _policy(threshold=2, confidence=0.7)
    low = [[_result("llm_judge", False, 0.5)], [_result("llm_judge", False, 0.6)]]
    high = [[_result("llm_judge", False, 0.8)], [_result("llm_judge", False, 0.9)]]
    mixed = [[_result("llm_judge", False, 0.6)], [_result("llm_judge", False, 0.8)]]

    assert evaluate_alert_policy([_run("FAIL"), _run("FAIL")], policy, low).should_alert is False
    assert evaluate_alert_policy([_run("FAIL"), _run("FAIL")], policy, high).should_alert is True
    assert evaluate_alert_policy([_run("FAIL"), _run("FAIL")], policy, mixed).should_alert is True


def test_mixed_failure_counts():
    policy = _policy(threshold=2, confidence=0.7)
    assert (
        evaluate_alert_policy(
            [_run("PASS"), _run("FAIL"), _run("FAIL")],
            policy,
            [[], [_result("llm_judge", False, 0.9)], [_result("llm_judge", False, 0.9)]],
        ).should_alert
        is True
    )
    assert (
        evaluate_alert_policy(
            [_run("PASS"), _run("FAIL"), _run("FAIL")],
            policy,
            [[], [_result("llm_judge", False, 0.5)], [_result("llm_judge", False, 0.6)]],
        ).should_alert
        is False
    )
    assert (
        evaluate_alert_policy(
            [_run("PASS"), _run("FAIL")], policy, [[], [_result("llm_judge", False, 0.9)]]
        ).should_alert
        is False
    )
