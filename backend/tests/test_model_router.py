"""Tests for model router."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.model_router import ModelRouter, ModelNotFoundError, AllProvidersUnavailableError
from app.services.providers.base import BaseProvider, ChatMessage, ChatResponse, StreamChunk, ModelDefinition


class MockProvider(BaseProvider):
    provider_name = "mock"

    def __init__(self, models=None):
        self._models = models or [
            ModelDefinition(id="mock-model-1", display_name="Mock 1", provider="mock"),
            ModelDefinition(id="mock-model-2", display_name="Mock 2", provider="mock"),
        ]

    async def chat(self, messages, model, max_tokens=4096, temperature=0.7):
        return ChatResponse(
            content="Hello from mock!",
            model=model,
            input_tokens=10,
            output_tokens=5,
        )

    async def stream(self, messages, model, max_tokens=4096, temperature=0.7):
        yield StreamChunk(text="Hello ")
        yield StreamChunk(text="from mock!")
        yield StreamChunk(finish_reason="stop", input_tokens=10, output_tokens=5)

    async def health_check(self):
        return True

    def available_models(self):
        return self._models


class FailingProvider(BaseProvider):
    provider_name = "failing"

    async def chat(self, messages, model, max_tokens=4096, temperature=0.7):
        raise Exception("Provider down!")

    async def stream(self, messages, model, max_tokens=4096, temperature=0.7):
        raise Exception("Provider down!")
        yield  # Make it a generator

    async def health_check(self):
        return False

    def available_models(self):
        return [ModelDefinition(id="fail-model", display_name="Failing", provider="failing")]


def test_register_provider():
    router = ModelRouter()
    provider = MockProvider()
    router.register_provider(provider)
    models = router.list_models()
    assert len(models) == 2
    assert models[0].id == "mock-model-1"


def test_resolve_model():
    router = ModelRouter()
    router.register_provider(MockProvider())
    mid, provider, defn = router.resolve_model("mock-model-1")
    assert mid == "mock-model-1"
    assert defn.display_name == "Mock 1"


def test_resolve_default_model():
    router = ModelRouter()
    router.register_provider(MockProvider())
    router.set_default_model("mock-model-2")
    mid, _, _ = router.resolve_model(None)
    assert mid == "mock-model-2"


def test_resolve_unknown_model():
    router = ModelRouter()
    router.register_provider(MockProvider())
    with pytest.raises(ModelNotFoundError):
        router.resolve_model("nonexistent")


@pytest.mark.asyncio
async def test_chat():
    router = ModelRouter()
    router.register_provider(MockProvider())
    messages = [ChatMessage(role="user", content="hi")]
    resp = await router.chat(messages, "mock-model-1")
    assert resp.content == "Hello from mock!"
    assert resp.input_tokens == 10


@pytest.mark.asyncio
async def test_stream():
    router = ModelRouter()
    router.register_provider(MockProvider())
    messages = [ChatMessage(role="user", content="hi")]
    chunks = []
    async for chunk in router.stream(messages, "mock-model-1"):
        chunks.append(chunk)
    assert len(chunks) == 3
    assert chunks[0].text == "Hello "
    assert chunks[1].text == "from mock!"


@pytest.mark.asyncio
async def test_health_check():
    router = ModelRouter()
    router.register_provider(MockProvider())
    health = await router.health_check()
    assert health["mock"] == True


@pytest.mark.asyncio
async def test_fallback_chain():
    router = ModelRouter()
    router.register_provider(FailingProvider())
    router.register_provider(MockProvider())
    router.set_fallback_chain("fail-model", ["mock-model-1"])

    messages = [ChatMessage(role="user", content="hi")]
    resp = await router.chat(messages, "fail-model")
    assert resp.content == "Hello from mock!"
