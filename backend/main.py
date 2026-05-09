from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.database import AsyncSessionLocal, init_db
from backend.engine.llm_judge import build_llm_judge_adapter
from backend.engine.scheduler import scheduler, start_scheduler
from backend.routers.runs import router as runs_router
from backend.routers.scenarios import router as scenarios_router
from backend.seed import seed_demo_scenarios


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str | None = None
    llm_judge_provider: str = "openai"
    llm_judge_model: str = ""
    database_url: str = "sqlite+aiosqlite:///./chirp.db"
    demo_mode: bool = False
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

app = FastAPI(title="Chirp API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://chirp.run"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(scenarios_router)
app.include_router(runs_router)


@app.on_event("startup")
async def startup_event():
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
    logger.info(
        "Chirp backend started",
        judge_provider=settings.llm_judge_provider if not settings.demo_mode else "demo_mode",
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "scheduler": "running" if scheduler.running else "stopped"}
