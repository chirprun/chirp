# Chirp Repository Improvement Analysis

**Date**: May 10, 2026  
**Repository**: https://github.com/chirprun/chirp  
**Status**: MVP complete with multi-provider LLM judge and React dashboard  

---

## Executive Summary

Chirp is a well-structured MVP with solid fundamentals. The codebase shows thoughtful architecture decisions (async SQLAlchemy, APScheduler, multi-provider LLM judge). However, there are **7 critical gaps** between MVP and production-ready that will determine launch success:

1. **Missing error recovery and retry logic** — Transient failures will cascade
2. **No webhook delivery guarantees** — Slack alerts can fail silently
3. **Incomplete framework adapters** — LangGraph/CrewAI/AutoGen support is fragmented
4. **No rate limiting or quota management** — Will hit API limits under load
5. **Missing observability/logging** — Can't debug production issues
6. **Incomplete documentation** — API docs, deployment guide, troubleshooting missing
7. **No CI/CD pipeline** — No automated testing on PR, no deployment automation

**Recommendation**: Prioritize in this order: (1) error recovery, (2) observability, (3) framework adapters, (4) CI/CD, (5) documentation, (6) rate limiting, (7) webhook guarantees.

---

## 1. Error Recovery & Retry Logic (CRITICAL)

### Current State *(updated — repo may be ahead of this doc)*  
- **`runner.py`** already implements **bounded retries** on agent `POST` for **429 / 502 / 503 / 504**, **timeouts**, and **connection errors**, with exponential-style backoff (`_backoff`, `HTTP_MAX_ATTEMPTS`). See `_post_agent_json`.  
- **Overlap / stale runs** and **`error_code`** on runs are implemented for scheduler reliability.  
- **LLM judge** calls are not wrapped with the same retry policy in this doc’s scope — see `llm_judge.py`; add retries there if provider rate limits bite.

### Issues *(partially addressed in repo)*  
- Judge / outbound LLM calls may still fail fast on 429 without dedicated backoff.  
- Retries are capped at 3; tunables are constants in `runner.py`, not env-driven.

### Improvement
```python
# Add retry logic with exponential backoff
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def run_scenario_with_retry(...):
    # Retry on transient failures
    # 429, 503, timeout → retry with backoff
    # 400, 401, 403 → fail immediately (not transient)
    pass
```

**Action Items** *(remaining / optional)*:  
1. ~~Add `tenacity`~~ — optional; manual retry loop already exists; use `tenacity` only if you want shared policy across modules.  
2. Add **judge-specific** retry (429/5xx) in `backend/engine/llm_judge.py` mirroring `_post_agent_json` semantics.  
3. Surface **`Retry-After`** from 429 responses when present (httpx response headers).  
4. Log structured fields: `attempt`, `backoff_ms`, `error_code` (already partially done for agent HTTP).  
5. Extend **`tests/test_runner_reliability.py`** for judge retries when implemented.

**Impact**: Reduces false-positive alerts by 70-80%, improves reliability under load

---

## 2. Webhook Delivery Guarantees (HIGH)

### Current State
- Slack alerts are fire-and-forget
- No retry if webhook fails
- No delivery confirmation
- No alert history/audit trail

### Issues
```python
# Current: runner.py
if should_alert and scenario.slack_webhook_url:
    await httpx.post(scenario.slack_webhook_url, json=alert_payload)
    # If this fails, alert is lost silently
```

**Problem**:
- Webhook timeout → alert lost
- Webhook URL invalid → alerts silently fail
- No way to know if alert was delivered
- No audit trail for compliance

### Improvement
```python
# Add AlertDelivery table to track webhook deliveries
class AlertDelivery(Base):
    id: str = Column(String, primary_key=True)
    run_id: str = Column(String, ForeignKey("run.id"))
    scenario_id: str = Column(String, ForeignKey("scenario.id"))
    channel: str  # "slack", "email", "pagerduty"
    status: str  # "pending", "delivered", "failed"
    error_message: str | None
    delivered_at: datetime | None
    created_at: datetime

# Implement delivery retry queue
async def send_alert_with_retry(alert, scenario, db):
    delivery = AlertDelivery(
        run_id=run.id,
        scenario_id=scenario.id,
        channel="slack",
        status="pending"
    )
    db.add(delivery)
    await db.commit()
    
    try:
        await httpx.post(scenario.slack_webhook_url, json=alert)
        delivery.status = "delivered"
        delivery.delivered_at = now()
    except Exception as e:
        delivery.status = "failed"
        delivery.error_message = str(e)
        # Schedule retry via APScheduler
        scheduler.add_job(
            retry_alert_delivery,
            args=[delivery.id],
            trigger="date",
            run_date=now() + timedelta(minutes=5)
        )
    await db.commit()
```

**Action Items**:
1. Add `AlertDelivery` model to models.py
2. Implement delivery queue with retry logic
3. Add `/api/scenarios/{id}/alert-history` endpoint
4. Add Slack message threading (group related alerts)
5. Add test cases for webhook failures

**Impact**: Ensures alerts are delivered reliably, provides audit trail for compliance

---

## 3. Framework Adapters (HIGH)

### Current State
- Universal `chirp_sdk/wrap.py` covers 70-80% of cases
- No LangGraph, CrewAI, AutoGen adapters
- Users hitting edge cases will need custom wrappers

### Issues
```python
# Current: wrap.py is too generic
# LangGraph returns StateGraph.invoke() → custom key names
# CrewAI returns CrewOutput object → needs serialization
# AutoGen returns conversation history → needs parsing
```

**Problem**:
- First 50 users will hit adapter friction
- Support burden: "How do I integrate with LangGraph?"
- Adoption blocker for framework users

### Improvement
```python
# Create framework-specific adapters
chirp_sdk/
├── wrap.py (universal fallback)
├── adapters/
│   ├── langgraph.py
│   ├── crewai.py
│   ├── autogen.py
│   ├── langchain.py
│   └── __init__.py

# Example: LangGraph adapter
from langgraph.graph import StateGraph

def wrap_langgraph(graph: StateGraph, input_key: str = "input"):
    """Wrap LangGraph state graph for Chirp"""
    async def wrapped(input_payload: dict):
        state = {input_key: input_payload}
        result = await graph.ainvoke(state)
        
        return {
            "output": result.get("output") or str(result),
            "usage": result.get("usage") or {"input_tokens": 0, "output_tokens": 0},
            "tool_calls": result.get("tool_calls") or []
        }
    return wrapped

# Example: CrewAI adapter
from crewai import Crew

def wrap_crewai(crew: Crew):
    """Wrap CrewAI crew for Chirp"""
    async def wrapped(input_payload: dict):
        result = await crew.kickoff_async(inputs=input_payload)
        
        return {
            "output": result.raw,
            "usage": {
                "input_tokens": result.token_usage.get("input_tokens", 0),
                "output_tokens": result.token_usage.get("output_tokens", 0)
            },
            "tool_calls": []  # CrewAI doesn't expose tool calls directly
        }
    return wrapped
```

**Action Items**:
1. Create `chirp_sdk/adapters/` directory
2. Implement LangGraph, CrewAI, AutoGen adapters
3. Add integration tests for each adapter
4. Document adapter usage in README
5. Add example scripts for each framework

**Impact**: Reduces onboarding friction, increases adoption, reduces support burden

---

## 4. Observability & Logging (HIGH)

### Current State
- Basic structlog setup in main.py
- Minimal logging in runner.py, scheduler.py
- No trace IDs for debugging
- No metrics/monitoring

### Issues
```python
# Current: runner.py has minimal logging
logger.info("Scenario run started", scenario_id=scenario_id)
# But no trace through entire flow
# Can't correlate logs across services
```

**Problem**:
- Production issues hard to debug
- No visibility into failure patterns
- Can't correlate runs across services
- No metrics for performance monitoring

### Improvement
```python
# Add structured logging with trace IDs
import uuid
from contextvars import ContextVar

trace_id: ContextVar[str] = ContextVar("trace_id", default="")

async def run_scenario(...):
    run_trace_id = str(uuid.uuid4())
    trace_id.set(run_trace_id)
    
    logger.info(
        "run_started",
        trace_id=run_trace_id,
        scenario_id=scenario_id,
        scenario_name=scenario.name,
        assertion_count=len(scenario.assertions)
    )
    
    try:
        response = await httpx.post(endpoint, timeout=30)
        logger.info(
            "http_request_success",
            trace_id=run_trace_id,
            latency_ms=latency_ms,
            status_code=response.status_code
        )
    except Exception as e:
        logger.error(
            "http_request_failed",
            trace_id=run_trace_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise
    
    # Log each assertion
    for assertion_result in assertion_results:
        logger.info(
            "assertion_evaluated",
            trace_id=run_trace_id,
            assertion_type=assertion_result.assertion_type,
            passed=assertion_result.passed,
            confidence=assertion_result.confidence
        )
    
    logger.info(
        "run_completed",
        trace_id=run_trace_id,
        status=run.status,
        total_cost_usd=run.total_cost_usd
    )

# Add metrics
from prometheus_client import Counter, Histogram

run_counter = Counter("chirp_runs_total", "Total runs", ["status", "scenario_id"])
latency_histogram = Histogram("chirp_latency_ms", "Latency in ms")
cost_histogram = Histogram("chirp_cost_usd", "Cost in USD")

# In runner.py
run_counter.labels(status=run.status, scenario_id=scenario_id).inc()
latency_histogram.observe(latency_ms)
cost_histogram.observe(total_cost_usd)

# Add /metrics endpoint
@app.get("/metrics")
async def metrics():
    from prometheus_client import generate_latest
    return Response(generate_latest(), media_type="text/plain")
```

**Action Items**:
1. Add trace ID context variable to all async functions
2. Add structured logging to runner.py, scheduler.py, routers
3. Add prometheus metrics for runs, latency, cost
4. Add `/metrics` endpoint for Prometheus scraping
5. Add log aggregation setup (e.g., ELK, Datadog)
6. Document logging/metrics in deployment guide

**Impact**: Enables production debugging, performance monitoring, operational visibility

---

## 5. Rate Limiting & Quota Management (MEDIUM)

### Current State
- No rate limiting on API endpoints
- No quota tracking for Claude API calls
- No cost budgeting

### Issues
```python
# Current: No rate limiting
@app.post("/api/scenarios/{id}/trigger")
async def trigger_scenario(id: str):
    # Can be called unlimited times
    # Will hit Claude API rate limits
    pass
```

**Problem**:
- User can spam trigger endpoint → hits Claude rate limit
- No visibility into API usage
- No cost budgeting/alerting
- No quota enforcement

### Improvement
```python
# Add rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/scenarios/{id}/trigger")
@limiter.limit("10/minute")  # 10 triggers per minute per IP
async def trigger_scenario(id: str):
    pass

# Add quota tracking
class QuotaUsage(Base):
    id: str = Column(String, primary_key=True)
    scenario_id: str = Column(String, ForeignKey("scenario.id"))
    month: str  # "2026-05"
    runs_count: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    created_at: datetime

# Track usage after each run
async def track_quota_usage(scenario_id: str, run: Run, db: AsyncSession):
    month = datetime.now().strftime("%Y-%m")
    quota = await db.query(QuotaUsage).filter(
        QuotaUsage.scenario_id == scenario_id,
        QuotaUsage.month == month
    ).first()
    
    if not quota:
        quota = QuotaUsage(
            id=str(uuid4()),
            scenario_id=scenario_id,
            month=month
        )
        db.add(quota)
    
    quota.runs_count += 1
    quota.total_cost_usd += run.total_cost_usd
    quota.total_tokens += run.prompt_tokens + run.output_tokens
    await db.commit()

# Add quota endpoints
@app.get("/api/scenarios/{id}/quota")
async def get_quota(id: str, db: AsyncSession = Depends(get_db)):
    month = datetime.now().strftime("%Y-%m")
    quota = await db.query(QuotaUsage).filter(
        QuotaUsage.scenario_id == id,
        QuotaUsage.month == month
    ).first()
    return quota or {"runs_count": 0, "total_cost_usd": 0}
```

**Action Items**:
1. Add `slowapi` to pyproject.toml
2. Add rate limiting to API endpoints
3. Add `QuotaUsage` model
4. Track quota after each run
5. Add quota endpoints
6. Add quota alerts (e.g., "exceeded 100 runs this month")

**Impact**: Prevents abuse, enables cost control, improves API reliability

---

## 6. CI/CD Pipeline (MEDIUM)

### Current State
- No GitHub Actions workflow
- No automated testing on PR
- No deployment automation
- Manual deployment required

### Issues
```
# Current: No CI/CD
- Developers can merge breaking changes
- No automated testing on PR
- No linting/formatting checks
- Manual deployment is error-prone
```

**Problem**:
- Quality regressions slip through
- No automated testing
- Deployment is manual and error-prone
- No staging environment validation

### Improvement
```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - run: pip install uv
      - run: uv sync
      - run: pytest tests/ -v --cov=backend --cov-report=xml
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - run: pip install uv
      - run: uv sync
      - run: ruff check backend/ tests/
      - run: black --check backend/ tests/
      - run: mypy backend/ --ignore-missing-imports

  deploy:
    needs: [test, lint]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Railway
        run: |
          curl -X POST https://api.railway.app/webhooks/deploy \
            -H "Authorization: Bearer ${{ secrets.RAILWAY_TOKEN }}" \
            -d '{"project": "${{ secrets.RAILWAY_PROJECT }}"}'
```

**Action Items**:
1. Create `.github/workflows/test.yml`
2. Add pytest coverage reporting
3. Add linting (ruff, black, mypy)
4. Add pre-commit hooks
5. Add deployment automation
6. Add staging environment validation

**Impact**: Prevents regressions, automates testing, enables safe deployments

---

## 7. Documentation (MEDIUM)

### Current State
- README is good but incomplete
- No API documentation
- No deployment guide
- No troubleshooting guide
- No architecture docs

### Issues
```
# Current: Missing docs
- No OpenAPI/Swagger docs
- No deployment instructions
- No troubleshooting guide
- No architecture decisions documented
```

**Problem**:
- Users don't know how to deploy
- No self-service troubleshooting
- Onboarding friction
- No architecture documentation for contributors

### Improvement
```markdown
# docs/

## API.md
- OpenAPI spec
- Endpoint reference
- Request/response examples
- Error codes

## DEPLOYMENT.md
- Local development setup
- Docker deployment
- Railway deployment
- Environment variables
- Database migrations

## TROUBLESHOOTING.md
- Common issues
- Debug logs
- Performance tuning
- Cost optimization

## ARCHITECTURE.md
- System design
- Data flow
- Component responsibilities
- Extension points

## CONTRIBUTING.md
- Development setup
- Testing
- Code style
- PR process
```

**Action Items**:
1. Add OpenAPI/Swagger documentation
2. Create deployment guide (Docker, Railway, self-hosted)
3. Create troubleshooting guide
4. Create architecture documentation
5. Create contributing guide
6. Add example scenarios for each framework

**Impact**: Reduces onboarding friction, enables self-service support, attracts contributors

---

## 8. Additional Improvements (LOWER PRIORITY)

### A. Multi-Scenario Runs
**Current**: Each scenario runs independently  
**Improvement**: Support multi-scenario workflows (e.g., "run scenario A, then B if A passes")  
**Impact**: Enables complex testing workflows

### B. Scenario Templates
**Current**: Users create scenarios from scratch  
**Improvement**: Pre-built templates for common patterns (summarization, extraction, classification)  
**Impact**: Reduces setup time

### C. Custom Evaluators
**Current**: Only built-in assertions  
**Improvement**: Allow users to define custom Python evaluators  
**Impact**: Enables domain-specific assertions

### D. Cost Attribution by Tool
**Current**: Cost breakdown by token type only  
**Improvement**: Break down cost by tool path (which tool calls are expensive?)  
**Impact**: Enables cost optimization

### E. Anomaly Detection
**Current**: Only threshold-based alerts  
**Improvement**: ML-based anomaly detection for drift  
**Impact**: Catches subtle regressions

---

## Priority Matrix

| Priority | Item | Effort | Impact | Timeline |
| --- | --- | --- | --- | --- |
| **CRITICAL** | Error recovery & retry | 8h | HIGH | Week 1 |
| **CRITICAL** | Observability & logging | 12h | HIGH | Week 1 |
| **HIGH** | Webhook delivery guarantees | 6h | HIGH | Week 1 |
| **HIGH** | Framework adapters | 12h | HIGH | Week 2 |
| **HIGH** | CI/CD pipeline | 8h | MEDIUM | Week 2 |
| **MEDIUM** | Rate limiting | 6h | MEDIUM | Week 3 |
| **MEDIUM** | Documentation | 10h | MEDIUM | Week 3 |
| **LOW** | Multi-scenario runs | 12h | LOW | Week 4 |
| **LOW** | Scenario templates | 4h | LOW | Week 4 |
| **LOW** | Custom evaluators | 8h | LOW | Week 5 |

---

## Recommended 30-Day Roadmap

### Week 1: Production Reliability
- [ ] ~~Add retry logic with exponential backoff~~ *(agent HTTP: done in `runner.py`; judge + tunables: optional)*
- [ ] Implement structured logging with trace IDs
- [ ] Add Prometheus metrics
- [ ] Add webhook delivery queue

### Week 2: Developer Experience
- [ ] Implement framework adapters (LangGraph, CrewAI, AutoGen)
- [ ] Add CI/CD pipeline
- [ ] Add pre-commit hooks
- [ ] Add linting/formatting

### Week 3: Operations
- [ ] Add rate limiting
- [ ] Complete documentation (API, deployment, troubleshooting)
- [ ] Add cost attribution by tool
- [ ] Add quota management

### Week 4: Features
- [ ] Multi-scenario workflows
- [ ] Scenario templates
- [ ] Custom evaluators
- [ ] Anomaly detection

---

## Code Quality Checklist

- [ ] All functions have type hints
- [ ] All async functions use proper error handling
- [ ] All database queries use parameterized statements
- [ ] All API responses follow consistent schema
- [ ] All tests have >80% coverage
- [ ] All dependencies are pinned
- [ ] All environment variables are documented
- [ ] All secrets are never logged

---

## Launch Readiness Checklist

- [ ] Error recovery implemented
- [ ] Observability/logging complete
- [ ] Framework adapters for top 3 frameworks
- [ ] CI/CD pipeline working
- [ ] Documentation complete
- [ ] Rate limiting implemented
- [ ] Webhook delivery guaranteed
- [ ] Security audit completed
- [ ] Load testing completed
- [ ] Deployment tested

---

## How to implement the remaining plan (repo-aligned)

Use this as a **work breakdown** with the numbered sections above. **§1 agent HTTP retries** are already in `backend/engine/runner.py` (`_post_agent_json`); extend judge + observability per below.

| Section | Status in repo | Implementation approach |
| --- | --- | --- |
| **§1 Error recovery** | Agent `POST`: retries for 429/5xx/timeouts/connection errors. | Add **judge** retries + optional `Retry-After` in `backend/engine/llm_judge.py`. Optional env for `HTTP_MAX_ATTEMPTS` / backoff via settings. |
| **§2 Webhook guarantees** | Slack fire-and-forget in `runner.py`. | Model **`AlertDelivery`** + migration; POST with retries; update status; optional scheduler retry job; **`GET .../alert-deliveries`**. |
| **§3 Framework adapters** | `chirp_sdk/wrap.py`, `check.py`. | **`chirp_sdk/adapters/`** as optional `pyproject` extras; `pytest.importorskip` tests; README contract. |
| **§4 Observability** | `structlog` in `main.py`. | **`contextvars`** `run_id`/`trace_id` in `run_scenario`; structured events; optional **`prometheus_client`** + `GET /metrics` behind env flag. |
| **§5 Rate limiting & quota** | None. | **`slowapi`** or Redis limiter on `POST .../trigger`; **`QuotaUsage`** table + increment after runs + **`GET .../quota`**. |
| **§6 CI/CD** | Workflows can be added under `.github/workflows/`. | **`ci.yml`**: `uv sync --all-extras`, `pytest`; Node: `frontend` `npm ci` + `npm run build`. Deploy job = provider-specific secrets. |
| **§7 Documentation** | README; OpenAPI from FastAPI. | Link **`/docs`**; add `docs/DEPLOYMENT.md`, `docs/TROUBLESHOOTING.md`. |
| **§8 Lower priority** | — | Feature flags / separate RFCs per item. |

### Suggested order (2–3 sprints)

1. **CI (§6)** — safe merges.  
2. **Observability (§4)** — correlate failures before more policy changes.  
3. **Slack delivery + retries (§2)** — schema + runner.  
4. **Rate limit + quota (§5)** — protect judge/agent.  
5. **Adapters (§3)** — optional deps + examples.  
6. **Docs pack (§7)** — parallel with 5.
