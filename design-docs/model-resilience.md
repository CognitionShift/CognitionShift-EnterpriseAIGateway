# Model Provider Resilience

## Problem

The gateway depends on external model providers (OpenAI, Anthropic, Google). Any of them can experience:

- Full outages (API down)
- Partial degradation (slow responses, elevated error rates)
- Rate limiting (429 responses)
- Capacity limits (503 responses)
- Network issues (timeouts, connection resets)

Users should never see "Service Unavailable" because one provider is having a bad day.

---

## Health Checking

### Active Health Checks

Every configured provider is health-checked on a regular interval:

```python
class ProviderHealthChecker:
    CHECK_INTERVAL = 30  # seconds
    TIMEOUT = 10  # seconds
    
    async def check(self, provider: ModelProvider) -> HealthStatus:
        try:
            start = time.monotonic()
            # Lightweight request — list models endpoint, not a completion
            response = await provider.client.get("/v1/models", timeout=self.TIMEOUT)
            latency_ms = (time.monotonic() - start) * 1000
            
            if response.status_code == 200:
                return HealthStatus(
                    status="healthy",
                    latency_ms=latency_ms,
                    checked_at=datetime.utcnow(),
                )
            elif response.status_code == 429:
                return HealthStatus(status="rate_limited", ...)
            else:
                return HealthStatus(status="degraded", ...)
        
        except (ConnectionError, TimeoutError):
            return HealthStatus(status="unreachable", ...)
```

### Passive Health Monitoring

Every real request updates the provider's health status:

```python
class PassiveHealthTracker:
    # Sliding window of recent request outcomes
    WINDOW_SIZE = 100
    ERROR_THRESHOLD = 0.3  # 30% error rate = degraded
    
    async def record(self, provider_id: str, success: bool, latency_ms: int):
        key = f"health:passive:{provider_id}"
        await redis.lpush(key, json.dumps({
            "success": success,
            "latency_ms": latency_ms,
            "at": time.time(),
        }))
        await redis.ltrim(key, 0, self.WINDOW_SIZE - 1)
    
    async def status(self, provider_id: str) -> str:
        key = f"health:passive:{provider_id}"
        results = await redis.lrange(key, 0, -1)
        
        if not results:
            return "unknown"
        
        recent = [json.loads(r) for r in results]
        error_rate = sum(1 for r in recent if not r["success"]) / len(recent)
        avg_latency = sum(r["latency_ms"] for r in recent) / len(recent)
        
        if error_rate > self.ERROR_THRESHOLD:
            return "degraded"
        elif avg_latency > 10000:  # >10s average
            return "slow"
        return "healthy"
```

### Health Status States

```
healthy      → Normal operation. Route traffic normally.
slow         → Elevated latency. Still functional but may affect UX.
degraded     → High error rate. Reduce traffic, prefer alternatives.
rate_limited → 429 responses. Back off, route to alternatives.
unreachable  → Cannot connect. Do not route traffic.
```

---

## Fallback Chains

Each model has an optional fallback chain configured by the admin:

```
Claude Opus → GPT-4o → Gemini 2.5 Pro → (error to user)
Claude Sonnet → GPT-4o-mini → (error to user)
GPT-4o → Claude Sonnet → Gemini 2.5 Pro → (error to user)
```

### Fallback Behavior

```python
class ModelRouter:
    async def resolve(self, requested_model: str, tenant: TenantContext) -> ResolvedModel:
        model = await self.get_model(requested_model, tenant.org_id)
        chain = self.build_fallback_chain(model)
        
        for candidate in chain:
            health = await self.health_tracker.status(candidate.provider_id)
            
            if health in ("healthy", "slow"):
                return candidate
            elif health == "rate_limited":
                # Try next, but this one might recover soon
                continue
            elif health in ("degraded", "unreachable"):
                continue
        
        # All providers in the chain are down
        raise AllProvidersUnavailableError(
            requested=requested_model,
            chain=[m.id for m in chain],
        )
    
    async def stream_with_fallback(self, model, messages, tenant):
        chain = self.build_fallback_chain(model)
        last_error = None
        
        for candidate in chain:
            try:
                async for chunk in candidate.provider.stream(messages):
                    yield chunk
                return  # Success, stop trying fallbacks
            
            except (ProviderError, TimeoutError) as e:
                last_error = e
                await self.health_tracker.record(candidate.provider_id, success=False, latency_ms=0)
                
                # If we already sent tokens to the client, we can't switch providers
                # The partial response is delivered with an error appended
                if chunk_count > 0:
                    yield ErrorChunk(f"Provider error after partial response: {e}")
                    return
                
                # No tokens sent yet — try next provider silently
                continue
        
        raise last_error
```

### User Notification on Fallback

**Key design decision:** When a fallback activates, do we tell the user?

**Yes, but subtly.** The response includes a metadata field indicating the actual model used:

```
data: {"type": "meta", "requested_model": "claude-opus", "actual_model": "gpt-4o", "reason": "fallback"}
```

The UI shows a small indicator: "Responded using GPT-4o (Claude Opus unavailable)". The user isn't blocked, and they know what model they're talking to.

---

## Retry Logic

Not all errors deserve a fallback. Some deserve a retry to the same provider:

```python
class RetryPolicy:
    MAX_RETRIES = 2
    RETRY_DELAY_BASE = 1.0  # seconds
    
    RETRYABLE_ERRORS = {
        429: "rate_limited",   # Retry with exponential backoff
        500: "server_error",   # Retry once
        502: "bad_gateway",    # Retry once
        503: "unavailable",    # Retry with backoff
    }
    
    NON_RETRYABLE_ERRORS = {
        400: "bad_request",
        401: "auth_error",
        403: "forbidden",
        404: "not_found",
    }
    
    async def execute_with_retry(self, fn, *args):
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await fn(*args)
            except ProviderHTTPError as e:
                if e.status_code not in self.RETRYABLE_ERRORS:
                    raise
                if attempt == self.MAX_RETRIES:
                    raise
                
                delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                if e.status_code == 429 and e.retry_after:
                    delay = max(delay, e.retry_after)
                
                await asyncio.sleep(delay)
```

**Order of operations:**
1. Try the requested provider (with retry for transient errors)
2. If the provider is consistently failing, try the fallback chain
3. If all providers fail, return an error to the user

---

## Circuit Breaker

Prevents sending traffic to a provider that's clearly down:

```python
class CircuitBreaker:
    FAILURE_THRESHOLD = 5      # failures before opening
    RECOVERY_TIMEOUT = 60      # seconds before half-open test
    
    # States: closed (normal) → open (blocking) → half-open (testing)
    
    async def call(self, provider_id: str, fn):
        state = await self.get_state(provider_id)
        
        if state == "open":
            if await self.recovery_timeout_elapsed(provider_id):
                # Half-open: try one request
                try:
                    result = await fn()
                    await self.close(provider_id)  # Success, recover
                    return result
                except Exception:
                    await self.open(provider_id)  # Still failing
                    raise CircuitOpenError(provider_id)
            else:
                raise CircuitOpenError(provider_id)
        
        try:
            result = await fn()
            await self.record_success(provider_id)
            return result
        except Exception as e:
            await self.record_failure(provider_id)
            if await self.failure_count(provider_id) >= self.FAILURE_THRESHOLD:
                await self.open(provider_id)
            raise
```

---

## Provider-Specific Considerations

| Provider | Quirks |
|----------|--------|
| **OpenAI** | Rate limits per-org and per-model. `Retry-After` header is reliable. Occasional 500s during high load. |
| **Anthropic** | Rate limits by token throughput, not just request count. May return partial responses on timeout. |
| **Google** | Gemini API has different error format. Rate limits are per-project. |
| **Ollama (self-hosted)** | No rate limits, but single-instance bottleneck. Health check via `/api/tags`. Queue depth matters more than error rate. |

The model router normalizes all provider responses and errors into a common format so the rest of the system doesn't care which provider is behind a model.
