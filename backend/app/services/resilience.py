"""Circuit breaker, retry with exponential backoff, and passive health monitoring."""

import asyncio
import json
import time
import structlog
from dataclasses import dataclass, field
from typing import Callable, Any

logger = structlog.get_logger()


# --- Circuit Breaker ---

class CircuitOpenError(Exception):
    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        super().__init__(f"Circuit open for provider: {provider_id}")


class CircuitBreaker:
    """Per-provider circuit breaker. States: closed → open → half-open → closed."""

    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 60  # seconds

    def __init__(self):
        self._states: dict[str, str] = {}  # provider_id → "closed"|"open"|"half_open"
        self._failure_counts: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def get_state(self, provider_id: str) -> str:
        state = self._states.get(provider_id, "closed")
        if state == "open":
            elapsed = time.monotonic() - self._opened_at.get(provider_id, 0)
            if elapsed >= self.RECOVERY_TIMEOUT:
                self._states[provider_id] = "half_open"
                return "half_open"
        return state

    def record_success(self, provider_id: str):
        self._failure_counts[provider_id] = 0
        self._states[provider_id] = "closed"

    def record_failure(self, provider_id: str):
        count = self._failure_counts.get(provider_id, 0) + 1
        self._failure_counts[provider_id] = count
        if count >= self.FAILURE_THRESHOLD:
            self._states[provider_id] = "open"
            self._opened_at[provider_id] = time.monotonic()
            logger.warning("circuit_opened", provider=provider_id, failures=count)

    def is_available(self, provider_id: str) -> bool:
        state = self.get_state(provider_id)
        return state in ("closed", "half_open")

    async def call(self, provider_id: str, fn: Callable, *args, **kwargs) -> Any:
        state = self.get_state(provider_id)
        if state == "open":
            raise CircuitOpenError(provider_id)

        try:
            result = await fn(*args, **kwargs)
            self.record_success(provider_id)
            return result
        except Exception as e:
            self.record_failure(provider_id)
            raise


# --- Retry with Exponential Backoff ---

RETRYABLE_STATUS_CODES = {429, 500, 502, 503}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}


class ProviderHTTPError(Exception):
    def __init__(self, status_code: int, message: str = "", retry_after: float | None = None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"Provider HTTP {status_code}: {message}")


async def retry_with_backoff(
    fn: Callable,
    *args,
    max_retries: int = 2,
    base_delay: float = 1.0,
    **kwargs,
) -> Any:
    """Execute fn with exponential backoff retry for transient errors."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except ProviderHTTPError as e:
            last_error = e
            if e.status_code in NON_RETRYABLE_STATUS_CODES:
                raise
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            if e.status_code == 429 and e.retry_after:
                delay = max(delay, e.retry_after)
            logger.info("retrying_provider", attempt=attempt + 1, delay=delay, status=e.status_code)
            await asyncio.sleep(delay)
        except Exception as e:
            last_error = e
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            logger.info("retrying_provider_generic", attempt=attempt + 1, delay=delay, error=str(e))
            await asyncio.sleep(delay)
    raise last_error


# --- Passive Health Monitoring ---

@dataclass
class HealthRecord:
    success: bool
    latency_ms: int
    at: float = field(default_factory=time.time)


class PassiveHealthTracker:
    """Sliding window health tracking per provider. In-memory for now."""

    WINDOW_SIZE = 100
    ERROR_THRESHOLD = 0.3  # 30% error rate = degraded
    SLOW_THRESHOLD_MS = 10000  # 10s average = slow

    def __init__(self):
        self._windows: dict[str, list[HealthRecord]] = {}

    def record(self, provider_id: str, success: bool, latency_ms: int):
        if provider_id not in self._windows:
            self._windows[provider_id] = []
        window = self._windows[provider_id]
        window.insert(0, HealthRecord(success=success, latency_ms=latency_ms))
        if len(window) > self.WINDOW_SIZE:
            self._windows[provider_id] = window[:self.WINDOW_SIZE]

    def status(self, provider_id: str) -> str:
        window = self._windows.get(provider_id, [])
        if not window:
            return "unknown"

        error_rate = sum(1 for r in window if not r.success) / len(window)
        avg_latency = sum(r.latency_ms for r in window) / len(window)

        if error_rate > self.ERROR_THRESHOLD:
            return "degraded"
        elif avg_latency > self.SLOW_THRESHOLD_MS:
            return "slow"
        return "healthy"

    def get_stats(self, provider_id: str) -> dict:
        window = self._windows.get(provider_id, [])
        if not window:
            return {"status": "unknown", "requests": 0}
        error_rate = sum(1 for r in window if not r.success) / len(window)
        avg_latency = sum(r.latency_ms for r in window) / len(window)
        return {
            "status": self.status(provider_id),
            "requests": len(window),
            "error_rate": round(error_rate, 3),
            "avg_latency_ms": round(avg_latency),
        }


# Global instances
circuit_breaker = CircuitBreaker()
health_tracker = PassiveHealthTracker()
