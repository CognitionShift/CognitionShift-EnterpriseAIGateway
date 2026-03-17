"""Anthropic Claude provider implementation."""

import anthropic
import structlog
from typing import AsyncIterator
from app.services.providers.base import (
    BaseProvider, ChatMessage, ChatResponse, StreamChunk, ModelDefinition
)

logger = structlog.get_logger()

ANTHROPIC_MODELS = [
    ModelDefinition(
        id="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        provider="anthropic",
        max_context_tokens=200000,
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        supports_vision=True,
    ),
    ModelDefinition(
        id="claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku",
        provider="anthropic",
        max_context_tokens=200000,
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.005,
        supports_vision=True,
    ),
    ModelDefinition(
        id="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        provider="anthropic",
        max_context_tokens=200000,
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
        supports_vision=True,
    ),
]


class AnthropicProvider(BaseProvider):
    provider_name = "anthropic"

    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.api_key = api_key

    def _convert_messages(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
        """Convert to Anthropic format, extracting system prompt."""
        system = None
        converted = []
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                converted.append({"role": msg.role, "content": msg.content})
        return system, converted

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:
        system, converted = self._convert_messages(messages)
        kwargs = {
            "model": model,
            "messages": converted,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return ChatResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "stop",
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        system, converted = self._convert_messages(messages)
        kwargs = {
            "model": model,
            "messages": converted,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        input_tokens = 0
        output_tokens = 0

        async with self.client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "message_start":
                    if hasattr(event, "message") and hasattr(event.message, "usage"):
                        input_tokens = event.message.usage.input_tokens
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield StreamChunk(text=event.delta.text)
                elif event.type == "message_delta":
                    if hasattr(event, "usage") and event.usage:
                        output_tokens = event.usage.output_tokens
                    finish = getattr(event.delta, "stop_reason", None) if hasattr(event, "delta") else None
                    yield StreamChunk(
                        finish_reason=finish,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )

    async def health_check(self) -> bool:
        try:
            # Minimal request to check connectivity
            response = await self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.warning("anthropic_health_check_failed", error=str(e))
            return False

    def available_models(self) -> list[ModelDefinition]:
        return ANTHROPIC_MODELS
