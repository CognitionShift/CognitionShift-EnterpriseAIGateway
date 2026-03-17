"""Unit tests for provider implementations (no real API calls)."""

import pytest
from app.services.providers.openai_provider import OpenAIProvider, OPENAI_MODELS
from app.services.providers.google_provider import GoogleProvider, GOOGLE_MODELS
from app.services.providers.anthropic_provider import AnthropicProvider, ANTHROPIC_MODELS


def test_openai_provider_models():
    """OpenAI provider should list GPT-4o, GPT-4o-mini, o3."""
    provider = OpenAIProvider(api_key="test-key")
    models = provider.available_models()
    ids = {m.id for m in models}
    assert "gpt-4o" in ids
    assert "gpt-4o-mini" in ids
    assert "o3" in ids
    assert provider.provider_name == "openai"

    # Check GPT-4o supports vision
    gpt4o = next(m for m in models if m.id == "gpt-4o")
    assert gpt4o.supports_vision is True
    assert gpt4o.max_context_tokens == 128000


def test_google_provider_models():
    """Google provider should list Gemini 2.5 Pro and Flash."""
    provider = GoogleProvider(api_key="test-key")
    models = provider.available_models()
    ids = {m.id for m in models}
    assert "gemini-2.5-pro" in ids
    assert "gemini-2.5-flash" in ids
    assert provider.provider_name == "google"

    # Check Gemini 2.5 Pro context size
    pro = next(m for m in models if m.id == "gemini-2.5-pro")
    assert pro.max_context_tokens == 1000000
    assert pro.supports_vision is True


def test_anthropic_provider_models():
    """Anthropic provider should list Claude models."""
    provider = AnthropicProvider(api_key="test-key")
    models = provider.available_models()
    ids = {m.id for m in models}
    assert len(ids) >= 3
    assert any("claude" in id for id in ids)
    assert provider.provider_name == "anthropic"


def test_provider_model_definitions():
    """All model definitions should have required fields."""
    all_models = OPENAI_MODELS + GOOGLE_MODELS + ANTHROPIC_MODELS
    for m in all_models:
        assert m.id, f"Model missing id: {m}"
        assert m.display_name, f"Model {m.id} missing display_name"
        assert m.provider, f"Model {m.id} missing provider"
        assert m.max_context_tokens > 0, f"Model {m.id} has invalid context size"
        assert m.input_cost_per_1k >= 0, f"Model {m.id} has negative input cost"
        assert m.output_cost_per_1k >= 0, f"Model {m.id} has negative output cost"


def test_openai_message_conversion():
    """Test message format conversion for OpenAI."""
    from app.services.providers.base import ChatMessage
    provider = OpenAIProvider(api_key="test-key")
    messages = [
        ChatMessage(role="system", content="You are helpful."),
        ChatMessage(role="user", content="Hello"),
    ]
    converted = provider._convert_messages(messages)
    assert len(converted) == 2
    assert converted[0]["role"] == "system"
    assert converted[1]["content"] == "Hello"


def test_google_message_conversion():
    """Test message format conversion for Google (extracts system instruction)."""
    from app.services.providers.base import ChatMessage
    provider = GoogleProvider(api_key="test-key")
    messages = [
        ChatMessage(role="system", content="Be concise."),
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi!"),
    ]
    system, contents = provider._convert_messages(messages)
    assert system == "Be concise."
    assert len(contents) == 2
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"  # Gemini uses "model" not "assistant"
