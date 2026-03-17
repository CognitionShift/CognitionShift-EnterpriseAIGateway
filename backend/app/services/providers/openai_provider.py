"""OpenAI provider implementation (GPT-4o, GPT-4o-mini, o3)."""

import httpx
import json
import structlog
from typing import AsyncIterator
from app.services.providers.base import (
    BaseProvider, ChatMessage, ChatResponse, StreamChunk, ModelDefinition
)

logger = structlog.get_logger()

OPENAI_MODELS = [
    ModelDefinition(
        id="gpt-4o",
        display_name="GPT-4o",
        provider="openai",
        max_context_tokens=128000,
        input_cost_per_1k=0.0025,
        output_cost_per_1k=0.01,
        supports_vision=True,
    ),
    ModelDefinition(
        id="gpt-4o-mini",
        display_name="GPT-4o Mini",
        provider="openai",
        max_context_tokens=128000,
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0006,
        supports_vision=True,
    ),
    ModelDefinition(
        id="o3",
        display_name="o3",
        provider="openai",
        max_context_tokens=200000,
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.04,
        supports_vision=False,
        supports_streaming=True,
    ),
]


class OpenAIProvider(BaseProvider):
    provider_name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    def _convert_messages(self, messages: list[ChatMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:
        payload = {
            "model": model,
            "messages": self._convert_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return ChatResponse(
            content=choice["message"]["content"],
            model=data.get("model", model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        payload = {
            "model": model,
            "messages": self._convert_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Usage info (sent with stream_options)
                usage = data.get("usage")
                if usage:
                    yield StreamChunk(
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                    )
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})
                finish = choice.get("finish_reason")

                text = delta.get("content", "")
                if text:
                    yield StreamChunk(text=text)
                if finish:
                    yield StreamChunk(finish_reason=finish)

    async def health_check(self) -> bool:
        try:
            response = await self.client.get("/models")
            return response.status_code == 200
        except Exception as e:
            logger.warning("openai_health_check_failed", error=str(e))
            return False

    def available_models(self) -> list[ModelDefinition]:
        return OPENAI_MODELS
