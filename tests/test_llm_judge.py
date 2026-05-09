from types import SimpleNamespace

from backend.engine.llm_judge import (
    AnthropicJudgeAdapter,
    OpenAICompatibleJudgeAdapter,
    build_llm_judge_adapter,
)


def test_build_judge_anthropic():
    adapter = build_llm_judge_adapter(
        SimpleNamespace(
            llm_judge_provider="anthropic",
            anthropic_api_key="sk-ant-test",
            openai_api_key="",
            openai_base_url=None,
            llm_judge_model="",
        )
    )
    assert isinstance(adapter, AnthropicJudgeAdapter)


def test_build_judge_openai():
    adapter = build_llm_judge_adapter(
        SimpleNamespace(
            llm_judge_provider="openai",
            anthropic_api_key="",
            openai_api_key="sk-openai-test",
            openai_base_url=None,
            llm_judge_model="",
        )
    )
    assert isinstance(adapter, OpenAICompatibleJudgeAdapter)


def test_build_judge_deepseek_uses_default_base():
    adapter = build_llm_judge_adapter(
        SimpleNamespace(
            llm_judge_provider="deepseek",
            anthropic_api_key="",
            openai_api_key="sk-deepseek-test",
            openai_base_url=None,
            llm_judge_model="",
        )
    )
    assert isinstance(adapter, OpenAICompatibleJudgeAdapter)
    assert "deepseek.com" in str(adapter._client.base_url)


def test_build_judge_missing_key_returns_none():
    assert (
        build_llm_judge_adapter(
            SimpleNamespace(
                llm_judge_provider="anthropic",
                anthropic_api_key="",
                openai_api_key="",
                openai_base_url=None,
                llm_judge_model="",
            )
        )
        is None
    )
