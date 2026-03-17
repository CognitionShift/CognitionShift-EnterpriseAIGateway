"""Model router — resolves model requests, manages providers, handles fallbacks."""

import time
import structlog
from typing import AsyncIterator
from app.services.providers.base import (
    BaseProvider, ChatMessage, ChatResponse, StreamChunk, ModelDefinition
)
from app.services.resilience import circuit_breaker, health_tracker, CircuitOpenError
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
        """Non-streaming chat with circuit breaker, passive health tracking, and fallback."""
        mid, provider, definition = self.resolve_model(model_id)
        chain = [mid] + self._fallback_chains.get(mid, [])

        for candidate_id in chain:
            try:
                _, cand_provider, _ = self.resolve_model(candidate_id)
                provider_name = cand_provider.provider_name

                # Skip if circuit is open
                if not circuit_breaker.is_available(provider_name):
                    logger.info("circuit_open_skipping", provider=provider_name, model=candidate_id)
                    continue

                start = time.monotonic()
                result = await cand_provider.chat(messages, candidate_id, max_tokens, temperature)
                latency = int((time.monotonic() - start) * 1000)

                # Record success
                circuit_breaker.record_success(provider_name)
                health_tracker.record(provider_name, success=True, latency_ms=latency)

                if candidate_id != mid:
                    logger.info("fallback_used", requested=mid, actual=candidate_id)
                return result
            except CircuitOpenError:
                continue
            except Exception as e:
                provider_name = self._model_map.get(candidate_id, ("unknown",))[0]
                circuit_breaker.record_failure(provider_name)
                health_tracker.record(provider_name, success=False, latency_ms=0)
                logger.warning("chat_failed_trying_fallback", model=candidate_id, error=str(e))
                continue

        raise AllProvidersUnavailableError(f"All providers failed for {mid}")

    async def stream(
        self,
        messages: list[ChatMessage],
        model_id: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat with circuit breaker, health tracking, and pre-stream fallback."""
        mid, provider, definition = self.resolve_model(model_id)
        chain = [mid] + self._fallback_chains.get(mid, [])

        for candidate_id in chain:
            try:
                _, cand_provider, _ = self.resolve_model(candidate_id)
                provider_name = cand_provider.provider_name

                if not circuit_breaker.is_available(provider_name):
                    logger.info("circuit_open_skipping_stream", provider=provider_name, model=candidate_id)
                    continue

                start = time.monotonic()
                chunk_count = 0

                # Emit fallback meta if using a different model
                if candidate_id != mid:
                    yield StreamChunk(text="")  # Signal that stream is starting
                    logger.info("stream_fallback_used", requested=mid, actual=candidate_id)

                async for chunk in cand_provider.stream(messages, candidate_id, max_tokens, temperature):
                    chunk_count += 1
                    yield chunk

                latency = int((time.monotonic() - start) * 1000)
                circuit_breaker.record_success(provider_name)
                health_tracker.record(provider_name, success=True, latency_ms=latency)
                return

            except CircuitOpenError:
                continue
            except Exception as e:
                provider_name = self._model_map.get(candidate_id, ("unknown",))[0]
                circuit_breaker.record_failure(provider_name)
                health_tracker.record(provider_name, success=False, latency_ms=0)
                logger.warning("stream_failed_trying_fallback", model=candidate_id, error=str(e))
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
