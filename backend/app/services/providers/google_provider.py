"""Google Gemini provider implementation (Gemini 2.5 Pro, Flash)."""

import httpx
import json
import structlog
from typing import AsyncIterator
from app.services.providers.base import (
    BaseProvider, ChatMessage, ChatResponse, StreamChunk, ModelDefinition
)

logger = structlog.get_logger()

GOOGLE_MODELS = [
    ModelDefinition(
        id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        provider="google",
        max_context_tokens=1000000,
        input_cost_per_1k=0.00125,
        output_cost_per_1k=0.005,
        supports_vision=True,
    ),
    ModelDefinition(
        id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        provider="google",
        max_context_tokens=1000000,
        input_cost_per_1k=0.000075,
        output_cost_per_1k=0.0003,
        supports_vision=True,
    ),
]


class GoogleProvider(BaseProvider):
    provider_name = "google"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    def _convert_messages(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
        """Convert to Gemini format, extracting system instruction."""
        system = None
        contents = []
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })
        return system, contents

    def _model_url(self, model: str, action: str) -> str:
        # Map our model IDs to Gemini API model names
        model_map = {
            "gemini-2.5-pro": "models/gemini-2.5-pro",
            "gemini-2.5-flash": "models/gemini-2.5-flash",
        }
        api_model = model_map.get(model, f"models/{model}")
        return f"{self.base_url}/{api_model}:{action}?key={self.api_key}"

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:
        system, contents = self._convert_messages(messages)
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = self._model_url(model, "generateContent")
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [{}])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)

        usage = data.get("usageMetadata", {})
        return ChatResponse(
            content=content,
            model=model,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            finish_reason=candidates[0].get("finishReason", "STOP").lower() if candidates else "stop",
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        system, contents = self._convert_messages(messages)
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = self._model_url(model, "streamGenerateContent") + "&alt=sse"

        async with self.client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts)
                    finish = candidates[0].get("finishReason")

                    if text:
                        yield StreamChunk(text=text)
                    if finish and finish != "STOP":
                        yield StreamChunk(finish_reason=finish.lower())

                usage = data.get("usageMetadata", {})
                if usage.get("candidatesTokenCount"):
                    yield StreamChunk(
                        finish_reason="stop",
                        input_tokens=usage.get("promptTokenCount", 0),
                        output_tokens=usage.get("candidatesTokenCount", 0),
                    )

    async def health_check(self) -> bool:
        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            response = await self.client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.warning("google_health_check_failed", error=str(e))
            return False

    def available_models(self) -> list[ModelDefinition]:
        return GOOGLE_MODELS
