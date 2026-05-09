from __future__ import annotations

import logging

import structlog
from anthropic import AsyncAnthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.database import AsyncSessionLocal, init_db
from backend.engine.scheduler import scheduler, start_scheduler
from backend.routers.runs import router as runs_router
from backend.routers.scenarios import router as scenarios_router
from backend.seed import seed_demo_scenarios


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./chirp.db"
    demo_mode: bool = False
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


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
    if not settings.anthropic_api_key and not settings.demo_mode:
        raise RuntimeError("ANTHROPIC_API_KEY is required unless DEMO_MODE=true")

    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_demo_scenarios(db)

    anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
    await start_scheduler(AsyncSessionLocal, anthropic_client)
    logger.info("Chirp backend started")


@app.get("/api/health")
async def health():
    return {"status": "ok", "scheduler": "running" if scheduler.running else "stopped"}
