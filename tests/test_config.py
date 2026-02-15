"""Test configuration loading."""

from openclaw.config import OpenClawConfig


def test_default_config():
    config = OpenClawConfig()
    assert config.port == 8340
    assert config.default_llm_provider == "groq"
    assert config.groq_model == "llama-3.3-70b-versatile"
    assert config.groq_daily_request_limit == 14000


def test_openrouter_config_defaults():
    config = OpenClawConfig()
    assert config.openrouter_api_key == ""
    assert config.openrouter_model == "anthropic/claude-sonnet-4"
    assert config.openrouter_daily_request_limit == 500
    assert config.openrouter_daily_token_limit == 500_000


def test_perplexity_config_defaults():
    config = OpenClawConfig()
    assert config.perplexity_api_key == ""
    assert config.perplexity_search_model == "sonar-pro"
