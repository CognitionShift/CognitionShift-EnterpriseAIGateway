"""Model router — resolves model requests, manages providers, handles fallbacks."""

import structlog
from typing import AsyncIterator
from app.services.providers.base import (
    BaseProvider, ChatMessage, ChatResponse, StreamChunk, ModelDefinition
)
from app.config import get_settings

logger = structlog.get_logger()


class ModelRouterError(Exception):
    pass


class ModelNotFoundError(ModelRouterError):
    pass


class AllProvidersUnavailableError(ModelRouterError):
    pass


class ModelRouter:
    """Central model router with provider management and fallback chains."""

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}
        self._model_map: dict[str, tuple[str, ModelDefinition]] = {}  # model_id -> (provider_name, definition)
        self._fallback_chains: dict[str, list[str]] = {}
        self._default_model: str | None = None

    def register_provider(self, provider: BaseProvider) -> None:
        """Register a model provider."""
        self._providers[provider.provider_name] = provider
        for model in provider.available_models():
            self._model_map[model.id] = (provider.provider_name, model)
        logger.info("provider_registered", provider=provider.provider_name, models=[m.id for m in provider.available_models()])

    def set_default_model(self, model_id: str) -> None:
        self._default_model = model_id

    def set_fallback_chain(self, model_id: str, fallbacks: list[str]) -> None:
        self._fallback_chains[model_id] = fallbacks

    def resolve_model(self, model_id: str | None) -> tuple[str, BaseProvider, ModelDefinition]:
        """Resolve a model ID to provider + definition."""
        mid = model_id or self._default_model
        if not mid:
            raise ModelNotFoundError("No model specified and no default configured")
        if mid not in self._model_map:
            raise ModelNotFoundError(f"Model '{mid}' not found. Available: {list(self._model_map.keys())}")
        provider_name, definition = self._model_map[mid]
        return mid, self._providers[provider_name], definition

    async def chat(
        self,
        messages: list[ChatMessage],
        model_id: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:
        """Non-streaming chat with fallback."""
        mid, provider, definition = self.resolve_model(model_id)
        try:
            return await provider.chat(messages, mid, max_tokens, temperature)
        except Exception as e:
            logger.warning("chat_failed_trying_fallback", model=mid, error=str(e))
            # Try fallback chain
            for fallback_id in self._fallback_chains.get(mid, []):
                try:
                    _, fb_provider, fb_def = self.resolve_model(fallback_id)
                    return await fb_provider.chat(messages, fallback_id, max_tokens, temperature)
                except Exception:
                    continue
            raise AllProvidersUnavailableError(f"All providers failed for {mid}")

    async def stream(
        self,
        messages: list[ChatMessage],
        model_id: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat with pre-stream fallback."""
        mid, provider, definition = self.resolve_model(model_id)
        try:
            async for chunk in provider.stream(messages, mid, max_tokens, temperature):
                yield chunk
        except Exception as e:
            logger.warning("stream_failed_trying_fallback", model=mid, error=str(e))
            for fallback_id in self._fallback_chains.get(mid, []):
                try:
                    _, fb_provider, fb_def = self.resolve_model(fallback_id)
                    async for chunk in fb_provider.stream(messages, fallback_id, max_tokens, temperature):
                        yield chunk
                    return
                except Exception:
                    continue
            raise AllProvidersUnavailableError(f"All providers failed for {mid}")

    def list_models(self) -> list[ModelDefinition]:
        """List all available models."""
        return [defn for _, defn in self._model_map.values()]

    async def health_check(self) -> dict[str, bool]:
        """Check health of all providers."""
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception:
                results[name] = False
        return results
