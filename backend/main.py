from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import RedirectResponse, Response

from backend.database import AsyncSessionLocal, init_db
from backend.engine.llm_judge import build_llm_judge_adapter
from backend.engine.scheduler import scheduler, start_scheduler
from backend.mcp_chirp import chirp_mcp, set_mcp_llm_judge_getter
from backend.rate_limit import limiter
from backend.routers.runs import router as runs_router
from backend.routers.scenarios import router as scenarios_router
from backend.routers.stream import router as stream_router
from backend.seed import seed_demo_scenarios


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str | None = None
    llm_judge_provider: str = "openai"
    llm_judge_model: str = ""
    database_url: str = "sqlite+aiosqlite:///./chirp.db"
    demo_mode: bool = False
    metrics_enabled: bool = Field(default=False, description="When true, expose GET /metrics for Prometheus")
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
logging.basicConfig(level=logging.INFO)
if not structlog.is_configured():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    )
logger = structlog.get_logger(__name__)

# Initialize MCP streamable HTTP session manager (lazy); mount this same app instance below.
mcp_http_app = chirp_mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run MCP Streamable HTTP session manager task group alongside API startup."""
    async with chirp_mcp.session_manager.run():
        if settings.demo_mode:
            app.state.llm_judge = None
        else:
            app.state.llm_judge = build_llm_judge_adapter(settings)
            if app.state.llm_judge is None:
                raise RuntimeError(
                    "LLM judge is not configured. Set DEMO_MODE=true, or set OPENAI_API_KEY "
                    "(default LLM_JUDGE_PROVIDER=openai; use LLM_JUDGE_PROVIDER=deepseek with the same key for DeepSeek), "
                    "or LLM_JUDGE_PROVIDER=anthropic with ANTHROPIC_API_KEY (optional OPENAI_BASE_URL)."
                )

        await init_db()
        async with AsyncSessionLocal() as db:
            await seed_demo_scenarios(db)

        await start_scheduler(AsyncSessionLocal, app.state.llm_judge)
        set_mcp_llm_judge_getter(lambda: app.state.llm_judge)
        logger.info(
            "Chirp backend started",
            judge_provider=settings.llm_judge_provider if not settings.demo_mode else "demo_mode",
        )
        yield


app = FastAPI(title="Chirp API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://chirp.run"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(scenarios_router)
app.include_router(runs_router)
app.include_router(stream_router)


@app.api_route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def mcp_redirect_trailing_slash(request: Request) -> RedirectResponse:
    """Streamable MCP is mounted at ``/mcp/``; clients often omit the trailing slash."""
    dest = "/mcp/"
    if request.url.query:
        dest = f"{dest}?{request.url.query}"
    return RedirectResponse(dest, status_code=307)


app.mount("/mcp/", mcp_http_app)


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/health")
async def health():
    return {"status": "ok", "scheduler": "running" if scheduler.running else "stopped"}
