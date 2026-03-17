"""CognitionShift Enterprise AI Gateway — Main Application."""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.services.model_router import ModelRouter
from app.services.providers.anthropic_provider import AnthropicProvider

settings = get_settings()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.debug else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global model router
model_router = ModelRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    logger.info("starting_gateway", environment=settings.environment)

    # Register Anthropic provider
    if settings.anthropic_api_key:
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
        model_router.register_provider(provider)
        model_router.set_default_model("claude-sonnet-4-20250514")
        # Set fallback chains
        model_router.set_fallback_chain("claude-opus-4-20250514", ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"])
        model_router.set_fallback_chain("claude-sonnet-4-20250514", ["claude-3-5-haiku-20241022"])
        logger.info("anthropic_provider_registered")
    else:
        logger.warning("no_anthropic_api_key")

    yield

    logger.info("shutting_down_gateway")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.chat import router as chat_router
from app.api.v1.models_api import router as models_router
from app.api.v1.usage import router as usage_router
from app.api.v1.admin.users import router as admin_users_router
from app.api.v1.admin.quotas import router as admin_quotas_router
from app.api.v1.admin.audit import router as admin_audit_router
from app.api.v1.admin.analytics import router as admin_analytics_router
from app.api.v1.admin.content_policy import router as admin_policy_router
from app.api.v1.admin.models import router as admin_models_router
from app.api.v1.files import router as files_router
from app.api.v1.search import router as search_router
from app.api.v1.knowledge_bases import router as kb_router
from app.api.v1.agents import router as agents_router

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(models_router, prefix="/api/v1")
app.include_router(usage_router, prefix="/api/v1")
app.include_router(admin_users_router, prefix="/api/v1")
app.include_router(admin_quotas_router, prefix="/api/v1")
app.include_router(admin_audit_router, prefix="/api/v1")
app.include_router(admin_analytics_router, prefix="/api/v1")
app.include_router(admin_policy_router, prefix="/api/v1")
app.include_router(admin_models_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(kb_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"name": settings.app_name, "version": "0.1.0", "docs": "/docs"}
