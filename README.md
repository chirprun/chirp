# Chirp

**The canary for AI agents in production.**

Chirp continuously monitors your AI agent for the failures that matter: bad answers, unsafe behavior, slow responses, and runaway cost.

```text
Status code says: 200 OK
Chirp says: quality down, latency breach, cost spike
```

Most monitoring tools tell you if your API is alive. Chirp tells you if your agent is still good.

---

## Why teams use Chirp

- **One signal, not five dashboards**: unified health across quality, safety, and cost
- **Continuous, not one-off**: scheduled synthetic runs against live endpoints
- **Actionable alerts**: failed assertions, confidence, latency, and cost in one message
- **Fast setup**: templates for solo builders, advanced controls for teams

---

## Core differentiator: Agent Health Score

Chirp computes a per-scenario **Agent Health Score** from:

- **Quality**: assertion pass rate + rubric-based semantic judging
- **Safety**: adversarial probe outcomes and policy checks
- **Efficiency**: latency and cost budget compliance

Every score includes drill-down evidence:

- exact failed checks
- confidence on `llm_judge`
- token/cost breakdown
- output + tool call trace

No black box. No hand-wavy “AI observability.”

---

## How Chirp works

1. Define a scenario (task, endpoint, schedule, assertions)
2. Chirp runs it on an interval
3. Assertions evaluate behavior
4. Health score updates
5. Alerts trigger on meaningful failure patterns

### Scenario example

```json
{
  "name": "Summarize quarterly report",
  "agent_endpoint": "https://your-agent.com/run",
  "input_payload": { "task": "Summarize this Q3 report..." },
  "schedule_minutes": 15,
  "assertions": [
    { "assertion_type": "latency_ms", "config": { "threshold_ms": 3000 } },
    { "assertion_type": "cost_usd", "config": { "threshold_usd": 0.05 } },
    { "assertion_type": "output_contains", "config": { "keyword": "revenue" } },
    { "assertion_type": "tool_call_sequence", "config": { "expected_sequence": ["search_kb", "format_response"] } },
    { "assertion_type": "llm_judge", "config": { "rubric": "Is this a coherent financial summary with key metrics?" } }
  ]
}
```

### Assertion types

- `latency_ms`: hard latency threshold
- `cost_usd`: budget guardrail
- `output_contains`: deterministic content check
- `tool_call_sequence`: expected tool behavior order
- `llm_judge`: semantic pass/fail with reason and confidence

### Noise-resistant alert policy

- alert after **N consecutive failures** (default: 2)
- suppress low-confidence semantic failures
- include failed checks + latency + cost context

---

## Built-in adversarial monitoring

Chirp can run adversarial probes as first-class scenarios:

- prompt-injection attempts
- role override attempts
- exfiltration-style prompts

This lets you continuously test guardrails, not just during pre-launch audits.

---

## How Chirp compares (honest)

Chirp is **worth building** if you care about a **small, sharp problem**: *on a schedule, does my deployed agent still pass explicit quality, safety, and cost checks on a fixed task?* It is **not** a replacement for full observability or full experiment platforms — it complements them.

### What Chirp is good at

- **Synthetic “canary tasks”** against a **real HTTP endpoint** (production or staging), not only offline evals.
- **Agent-native assertions** in one bundle: latency, **token-ish cost**, string checks, **tool order**, **LLM rubric judge**, plus **adversarial-style** scenarios.
- **Opinionated alert policy** (consecutive failures + judge confidence) to reduce noise.
- **Self-hostable, small footprint** — you can read the code and reason about behavior end-to-end.

### What Chirp is not (yet)

- **Not Datadog-class APM**: no fleet-wide infra metrics, RUM, or enterprise incident workflows. Chirp does not replace Datadog for **platform** health.
- **Not LangSmith / Langfuse-class tracing**: no rich distributed trace UI, span waterfall, or deep runtime auto-instrumentation for every framework.
- **Not Braintrust-class experiment UI**: no full dataset versioning, human review queues, or large-scale offline experiment matrix — use those tools where that depth matters.
- **Production wiring is yours**: the runner calls **`POST` + JSON** today; auth to your agent is usually an **adapter** or gateway pattern (custom headers on scenarios are a natural next step if you need them).
- **Judge and probes are imperfect**: `llm_judge` costs money and can be wrong; confidence filtering helps but is not a guarantee. Adversarial probes are **signals**, not a formal security certification.

### One-line question each tool family optimizes for

| Family | Core question |
|--------|----------------|
| **Datadog (and classic synthetics)** | Is the **service / HTTP path** healthy and within SLO? |
| **LangSmith** | What happened inside this **LangChain/LangGraph** run, and how do I **debug and evaluate** it? |
| **Langfuse** (and similar OSS trace tools) | How do I **collect, query, and score** traces and prompts in production? |
| **Braintrust / eval harnesses** | How good is this **model or prompt** on **datasets** and in **CI**? |
| **Chirp** | On a **timer**, does my **deployed agent endpoint** still meet **explicit** quality, safety, and cost checks on a **representative task**? |

### Practical stance

- Use **Datadog** (or equivalents) for **pipes, pods, and APIs**.
- Use **LangSmith / Langfuse / Phoenix** when you need **trace-first** debugging and rich analytics.
- Use **Chirp** (or build this pattern) when you want **scheduled agent canaries** with **bespoke assertions** without standing up the whole observability product surface area first.

That overlap is **healthy**: Chirp should stay **narrow and excellent** at scheduled agent contracts, not try to become another full observability vendor overnight.

---

## Quick start (local dev)

```bash
# 1) Configure environment (see .env.example for judge keys: OpenAI, DeepSeek, or Anthropic)
cp .env.example .env

# 2) Install Python deps (include dev for pytest)
uv sync --extra dev

# 3) Start backend + mock agent
uv run uvicorn backend.main:app --reload --port 8000
uv run uvicorn mock_agent.main:app --port 8001 --reload

# 4) Optional: dashboard (http://localhost:5173 — proxies /api to the backend)
cd frontend && npm install && npm run dev

# 5) Health check
curl http://localhost:8000/api/health
```

Trigger a scenario manually:

```bash
curl -X POST http://localhost:8000/api/scenarios/{id}/trigger
```

Simulate failures via mock chaos modes:

```bash
curl -X POST http://localhost:8001/chaos/slow
curl -X POST http://localhost:8001/chaos/degraded
curl -X POST http://localhost:8001/chaos/expensive
curl -X POST http://localhost:8001/chaos/injected
curl -X POST http://localhost:8001/chaos/healthy
```

---

## Agent response contract

Your endpoint should return:

```json
{
  "output": "The quarterly revenue grew 12% YoY...",
  "usage": {
    "input_tokens": 150,
    "output_tokens": 280
  },
  "tool_calls": [
    { "name": "search_kb" },
    { "name": "format_response" }
  ]
}
```

If your shape differs, wrap your agent:

```python
from chirp_sdk.wrap import wrap

wrapped_agent = wrap(my_agent_fn)
```

---

## Who Chirp is for

- solo builders shipping AI features quickly
- small product teams running production agents
- safety and quality teams that need continuous evidence

---

## Architecture

```text
chirp/
├── backend/
│   ├── engine/
│   │   ├── assertions.py
│   │   ├── llm_judge.py
│   │   ├── runner.py
│   │   ├── scheduler.py
│   │   ├── alert_policy.py
│   │   └── probes.py
│   ├── routers/
│   │   ├── scenarios.py
│   │   ├── runs.py
│   │   └── stream.py      # SSE: scenario check stream
│   ├── mcp_chirp.py       # MCP tools/resources (mounted at /mcp/)
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── seed.py
│   └── main.py
├── frontend/              # Vite + React; src/chirp-ui/ streaming components
├── mock_agent/
├── chirp_sdk/
└── tests/
```

**Stack:** Python 3.11, FastAPI, SQLAlchemy async, SQLite, APScheduler, httpx, MCP (FastMCP streamable HTTP at `/mcp/`), OpenAI SDK (LLM judge; optional Anthropic), pytest · React, Vite, Recharts (dashboard)

**Agent contract SDK:** `from chirp_sdk import check, wrap` — `check(agent_fn, payload)` runs one invocation and returns the Chirp-shaped dict your HTTP agent should emit.

**MCP:** Point an MCP client at `http://<api-host>:<port>/mcp/` (streamable HTTP). Requests to `/mcp` (no trailing slash) are redirected to `/mcp/`. Tools: `chirp_list_scenarios`, `chirp_get_scenario`, `chirp_check`, `chirp_get_run`, `chirp_list_runs`. Resources: `chirp://scenarios`, `chirp://scenario/{id}`.

**SSE UI pattern:** `GET /api/scenarios/{id}/check-stream` emits `thinking` then `response` events; the dashboard “Stream check” button uses `frontend/src/chirp-ui/ThinkingResponseStream.tsx`.

---

## Roadmap

Themes stay the same; this section scopes what “done” roughly means so planning and contributions line up.

### Near-term

- **Framework adapters (LangGraph, CrewAI, AutoGen)**  
  - Publish a **contract doc** for the JSON shape Chirp already assumes (`output`, `usage`, `tool_calls`, optional `tool_cost_usd`).  
  - Per framework: a **minimal “wrap your graph/run”** pattern (single POST handler or last-node callback) that maps native traces to that contract—no requirement to run frameworks inside Chirp.  
  - Stretch: tiny optional helper modules only where a shared pattern exists across versions.

- **GitHub Actions regression gates**  
  - Reusable workflow: **start API + DB**, **seed or target scenario IDs**, **poll run to terminal status**, **fail job** on `FAIL` / `ERROR` or on specific `error_code`.  
  - Document **secrets** (judge keys, agent URLs) and **when to run** (smoke on PR vs nightly full matrix).

- **Expanded adversarial probe packs**  
  - More probes in `backend/engine/probes.py` with **categories** (injection, exfil, policy bypass) and optional **severity** metadata.  
  - Scenario-level or global **filters** so teams can tune aggressiveness without forking code.

- **More alert channels (email, PagerDuty)**  
  - Small **notifier abstraction** next to Slack (same policy engine, different transport).  
  - Config on scenario or global settings: channel type + endpoint/credentials; keep Slack as default path.

- **Optional auth headers / mTLS for agent `POST`**  
  - Scenario-scoped **header map** (e.g. `Authorization`, `X-API-Key`) passed through `httpx` on the agent client.  
  - Optional **client cert / CA** paths for mTLS, with clear docs for reverse proxies vs direct agent TLS.

### Later

- **Self-hosted deployment profile**  
  - **Compose** (or similar) for API + scheduler + volume-mounted SQLite, **health/readiness** routes, env checklist for production.  
  - Optional split: dashboard static build behind same origin or CDN.

- **Anomaly detection for behavior drift**  
  - Rolling windows over **pass rate, latency, cost** per scenario; **threshold or z-score** style alerts when distribution shifts vs baseline.  
  - Requires durable history and possibly aggregation tables or external TSDB—scope TBD.

- **Cost attribution by tool path**  
  - Richer parsing of **nested or ordered** `tool_calls` (and framework-specific shapes once adapters exist) to roll up cost by **tool name or path**.  
  - Assertions or reports that flag **which branch** of behavior drove spend.

- **Multi-agent flow monitoring**  
  - Model **ordered or DAG sub-steps** (handoffs, reviewer agents) as one scenario or linked scenarios with a **shared correlation id** in payloads.  
  - Assertions that can target **per-hop** outputs or cumulative trace.

- **Postgres profile for multi-instance API**  
  - First-class **`DATABASE_URL`** for async Postgres, pool tuning, and **migration strategy** from default SQLite.  
  - Scheduler assumptions revisited for **multi-worker** (run locking / advisory locks) so overlapping instances do not double-schedule.

### MCP / protocol integrations (status)

- **Chirp as MCP server (shipped):** FastMCP **streamable HTTP** is mounted at **`/mcp/`** on the API app (`backend/mcp_chirp.py`); **`/mcp`** redirects with **307** so clients work with or without a trailing slash. Tools mirror REST: list/get scenarios, **`chirp_check`** (full run + assertions), get/list runs. Resources: **`chirp://scenarios`**, **`chirp://scenario/{scenario_id}`**.
- **Agent transport:** Scheduled checks still **`POST` JSON to `agent_endpoint`** (`backend/engine/runner.py`). MCP is for **operators and LLM clients** querying Chirp, not a replacement for the agent wire protocol unless you add a bridge.
- **Still under consideration:** optional **MCP client hook inside the runner** (call remote tools around the agent step) and documented **HTTP↔MCP bridges** for MCP-only agents.

---

## Contributing

```bash
uv run pytest -v
cd frontend && npm ci && npm run build
```

**Dashboard “Stream check”:** the UI calls `GET /api/scenarios/{id}/check-stream` on the same origin as the app. With **`npm run dev`**, Vite proxies `/api` to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8000`); copy `frontend/.env.example` to `frontend/.env` if your API uses another port. With **`npm run preview`**, the same proxy applies—without it, `/api/...` returns **404** and streaming fails.

---

## License

MIT

---

Built by [@swpnk](https://linkedin.com/in/swapnikchimalamarri) · [chirp.run](https://chirp.run)
