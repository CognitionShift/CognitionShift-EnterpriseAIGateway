"""Base provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class StreamChunk:
    text: str = ""
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class ChatResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str = "stop"


@dataclass
class ModelDefinition:
    id: str
    display_name: str
    provider: str
    max_context_tokens: int = 200000
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    supports_streaming: bool = True
    supports_vision: bool = False


class BaseProvider(ABC):
    """Abstract base for all model providers."""

    provider_name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:
        """Non-streaming chat completion."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion yielding chunks."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is reachable."""
        ...

    @abstractmethod
    def available_models(self) -> list[ModelDefinition]:
        """List available models for this provider."""
        ...
