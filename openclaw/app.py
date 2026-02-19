"""FastAPI application factory — wires everything together."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openclaw import __version__
from openclaw.config import OpenClawConfig
from openclaw.connectors.cmms import CMMSConnector
from openclaw.connectors.jarvis import JarvisConnector
from openclaw.connectors.matrix import MatrixConnector
from openclaw.connectors.plc import PLCConnector
from openclaw.gateway.http_api import router as api_router, set_dispatch
from openclaw.gateway.rate_limit import RateLimiter
from openclaw.gateway.telegram import TelegramAdapter
from openclaw.llm.budget import BudgetTracker
from openclaw.llm.providers.anthropic import AnthropicProvider
from openclaw.llm.providers.gemini import GeminiProvider
from openclaw.llm.providers.groq import GroqProvider
from openclaw.llm.providers.nvidia import NvidiaProvider
from openclaw.llm.providers.openai import OpenAIProvider
from openclaw.llm.providers.deepseek import DeepSeekProvider
from openclaw.llm.providers.openrouter import OpenRouterProvider
from openclaw.llm.router import LLMRouter
from openclaw.messages.intent import classify
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.observability.health import aggregate_health
from openclaw.observability.metrics import MetricsCollector
from openclaw.skills.base import SkillContext
from openclaw.skills.registry import SkillRegistry
from openclaw.types import Channel, Intent

logger = logging.getLogger(__name__)


def create_app(config: OpenClawConfig | None = None) -> FastAPI:
    """Build and return the FastAPI application."""
    if config is None:
        config = OpenClawConfig.from_yaml()

    app = FastAPI(title="OpenClaw", version=__version__, docs_url="/docs")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # -- LLM Providers --
    providers: dict = {}
    if config.groq_api_key:
        providers["groq"] = GroqProvider(config.groq_api_key, config.groq_model)
    if config.nvidia_api_key:
        providers["nvidia"] = NvidiaProvider(config.nvidia_api_key, config.nvidia_model, config.nvidia_fallback_model)
    if config.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(config.anthropic_api_key, config.anthropic_model)
    if config.openai_api_key:
        providers["openai"] = OpenAIProvider(config.openai_api_key, config.openai_model)
    if config.gemini_api_key:
        providers["gemini"] = GeminiProvider(config.gemini_api_key, config.gemini_model)
    if config.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(config.openrouter_api_key, config.openrouter_model)
    if config.deepseek_api_key:
        providers["deepseek"] = DeepSeekProvider(config.deepseek_api_key, config.deepseek_model)

    budget = BudgetTracker()
    if config.groq_daily_request_limit:
        budget.configure("groq", daily_request_limit=config.groq_daily_request_limit)
    if config.openrouter_daily_request_limit or config.openrouter_daily_token_limit:
        budget.configure(
            "openrouter",
            daily_request_limit=config.openrouter_daily_request_limit,
            daily_token_limit=config.openrouter_daily_token_limit,
        )

    llm_router = LLMRouter(providers, budget)

    # -- Connectors --
    connectors: dict = {}
    if config.matrix_url:
        matrix = MatrixConnector(config.matrix_url)
        connectors["matrix"] = matrix
    if config.jarvis_hosts:
        connectors["jarvis"] = JarvisConnector(config.jarvis_hosts)
    if config.cmms_url:
        connectors["cmms"] = CMMSConnector(config.cmms_url, config.cmms_email, config.cmms_password)
    if config.plc_host:
        connectors["plc"] = PLCConnector(config.plc_host, config.plc_port)
    if config.kb_enabled and config.kb_postgres_url:
        from openclaw.connectors.knowledge import KnowledgeConnector
        connectors["knowledge"] = KnowledgeConnector(config.kb_postgres_url)
    if config.maint_llm_enabled and config.maint_llm_url:
        from openclaw.connectors.maintenance_llm import MaintenanceLLMConnector
        connectors["maintenance_llm"] = MaintenanceLLMConnector(config.maint_llm_url)

    # -- Skills --
    registry = SkillRegistry()
    registry.register_builtins()

    # -- Metrics --
    metrics = MetricsCollector()

    # -- Rate Limiter --
    rate_limiter = RateLimiter(config.telegram_rate_limit_per_hour)

    # -- Skill Context --
    skill_context = SkillContext(llm=llm_router, connectors=connectors, config=config, metrics=metrics)

    # -- Central dispatch --
    async def dispatch(message: InboundMessage) -> OutboundMessage:
        """Central message dispatch: classify → route → skill → respond."""
        # Classify intent if not already set
        if message.intent == Intent.UNKNOWN:
            message.intent = classify(message)

        logger.info("Dispatch: user=%s intent=%s text=%s", message.user_id, message.intent.value, message.text[:80])

        # Find skill
        skill = registry.get(message.intent)
        if not skill:
            skill = registry.get(Intent.CHAT)
        if not skill:
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="No skill available to handle this request.",
            )

        try:
            response = await skill.handle(message, skill_context)
            metrics.record_request(message.intent.value)
            return response
        except Exception:
            logger.exception("Skill %s failed", skill.name())
            return OutboundMessage(
                channel=message.channel, user_id=message.user_id,
                text="An error occurred processing your request. Please try again.",
            )

    # -- Wire HTTP API --
    set_dispatch(dispatch)
    app.include_router(api_router)

    # -- Health endpoint --
    @app.get("/health")
    async def health():
        return await aggregate_health(connectors)

    @app.get("/metrics")
    async def get_metrics():
        return metrics.summary()

    @app.get("/")
    async def root():
        return {
            "name": "OpenClaw",
            "version": __version__,
            "providers": list(providers.keys()),
            "skills": [s.name() for s in registry.all_skills()],
        }

    # -- Lifecycle --
    telegram_adapter: TelegramAdapter | None = None

    @app.on_event("startup")
    async def startup():
        nonlocal telegram_adapter
        # Connect all connectors
        for conn in connectors.values():
            try:
                await conn.connect()
            except Exception:
                logger.exception("Failed to connect %s", conn.name())

        # Start Telegram if configured
        if config.telegram_enabled and config.telegram_bot_token:
            telegram_adapter = TelegramAdapter(
                config.telegram_bot_token, dispatch,
                allowed_users=config.telegram_allowed_users or None,
                openai_api_key=config.openai_api_key,
            )
            try:
                await telegram_adapter.start()
                app.state.telegram_adapter = telegram_adapter
                # Wire Telegram send into skill context for background notifications
                skill_context._telegram_send = telegram_adapter.send
            except Exception:
                logger.exception("Failed to start Telegram adapter")

        logger.info("OpenClaw %s started on %s:%d", __version__, config.host, config.port)
        logger.info("LLM providers: %s", ", ".join(providers.keys()) or "none")
        logger.info("Connectors: %s", ", ".join(connectors.keys()))
        logger.info("Skills: %s", ", ".join(s.name() for s in registry.all_skills()))

    @app.on_event("shutdown")
    async def shutdown():
        if telegram_adapter:
            await telegram_adapter.stop()
        for conn in connectors.values():
            await conn.disconnect()

    # Store references for testing
    app.state.dispatch = dispatch
    app.state.config = config
    app.state.llm_router = llm_router
    app.state.registry = registry
    app.state.telegram_adapter = None

    return app
