from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScenarioAssertionCreate(BaseModel):
    assertion_type: str = Field(..., description="Assertion type identifier")
    config: dict = Field(default_factory=dict, description="Assertion config payload")


class ScenarioCreate(BaseModel):
    name: str = Field(..., description="Scenario name")
    description: str | None = Field(default=None, description="Scenario description")
    agent_endpoint: str = Field(..., description="Agent endpoint URL")
    input_payload: dict = Field(default_factory=dict, description="Payload sent to monitored agent")
    schedule_minutes: int = Field(default=15, description="Schedule interval in minutes")
    scenario_type: str = Field(default="standard", description="Scenario type")
    slack_webhook_url: str | None = Field(default=None, description="Slack webhook for alerts")
    assertions: list[ScenarioAssertionCreate] = Field(default_factory=list)


class ScenarioResponse(BaseModel):
    id: str
    name: str
    description: str | None
    agent_endpoint: str
    schedule_minutes: int
    scenario_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    assertions: list[dict]
    last_run_status: str | None = None
    last_run_timestamp: datetime | None = None
    last_latency_ms: int | None = None
    last_cost_usd: float | None = None


class AssertionResultResponse(BaseModel):
    id: str
    assertion_type: str
    passed: bool
    expected: str
    actual: str
    detail: str
    confidence: float | None = None


class RunResponse(BaseModel):
    id: str
    scenario_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    latency_ms: int | None
    prompt_cost_usd: float | None
    tool_cost_usd: float | None
    response_cost_usd: float | None
    total_cost_usd: float | None
    error_message: str | None
    assertion_results: list[AssertionResultResponse]


class QualityTrendPoint(BaseModel):
    hour: str = Field(..., description="Hour in ISO format")
    quality_score: float = Field(..., description="Quality score 0-100")


class CostTrendPoint(BaseModel):
    run_id: str
    prompt_cost: float
    tool_cost: float
    response_cost: float


class TemplateResponse(BaseModel):
    name: str
    description: str
    suggested_assertions: list[dict]
