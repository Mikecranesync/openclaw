"""Test configuration loading."""

from openclaw.config import OpenClawConfig


def test_default_config():
    config = OpenClawConfig()
    assert config.port == 8340
    assert config.default_llm_provider == "groq"
    assert config.groq_model == "llama-3.3-70b-versatile"
    assert config.groq_daily_request_limit == 14000
