from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AlertDecision:
    should_alert: bool
    reason: str


def evaluate_alert_policy(
    recent_runs: list,
    policy,
    recent_assertion_results: list[list],
) -> AlertDecision:
    if not recent_runs:
        return AlertDecision(False, "No runs available")

    trailing_failures = 0
    failing_indexes: list[int] = []
    for idx in range(len(recent_runs) - 1, -1, -1):
        status = getattr(recent_runs[idx], "status", "")
        if status in {"FAIL", "ERROR"}:
            trailing_failures += 1
            failing_indexes.append(idx)
        else:
            break

    if trailing_failures < int(policy.consecutive_failures_threshold):
        return AlertDecision(False, "Not enough consecutive failures")

    llm_conf_threshold = float(policy.llm_judge_confidence_threshold)
    llm_results = []
    for idx in failing_indexes:
        if idx >= len(recent_assertion_results):
            continue
        for result in recent_assertion_results[idx]:
            if getattr(result, "assertion_type", "") == "llm_judge":
                llm_results.append(result)

    if llm_results and all((getattr(r, "confidence", 0.0) or 0.0) < llm_conf_threshold for r in llm_results):
        return AlertDecision(False, "LLM judge confidence too low")

    return AlertDecision(True, f"{trailing_failures} consecutive failures")
