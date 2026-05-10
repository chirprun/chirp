"""Framework-oriented helpers (duck-typed; no hard dependency on LangGraph/CrewAI/AutoGen)."""

from chirp_sdk.adapters.autogen import wrap_autogen_chat
from chirp_sdk.adapters.crewai import wrap_crewai
from chirp_sdk.adapters.langgraph import wrap_langgraph

__all__ = ["wrap_autogen_chat", "wrap_crewai", "wrap_langgraph"]
