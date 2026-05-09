from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_endpoint: Mapped[str] = mapped_column(String, nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    schedule_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    scenario_type: Mapped[str] = mapped_column(String, nullable=False, default="standard")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    slack_webhook_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    assertions: Mapped[list["ScenarioAssertion"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    alert_policy: Mapped["AlertPolicy | None"] = relationship(
        back_populates="scenario", uselist=False, cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship(back_populates="scenario", cascade="all, delete-orphan")


class ScenarioAssertion(Base):
    __tablename__ = "scenario_assertions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), nullable=False, index=True)
    assertion_type: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    scenario: Mapped["Scenario"] = relationship(back_populates="assertions")


class AlertPolicy(Base):
    __tablename__ = "alert_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id"), nullable=False, unique=True, index=True
    )
    consecutive_failures_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    llm_judge_confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    scenario: Mapped["Scenario"] = relationship(back_populates="alert_policy")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="RUNNING")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    tool_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    scenario: Mapped["Scenario"] = relationship(back_populates="runs")
    assertion_results: Mapped[list["AssertionResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AssertionResult(Base):
    __tablename__ = "assertion_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    assertion_type: Mapped[str] = mapped_column(String, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected: Mapped[str] = mapped_column(Text, nullable=False)
    actual: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="assertion_results")
