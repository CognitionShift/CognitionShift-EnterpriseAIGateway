# Streaming Architecture

## The Problem

Chat AI responses stream token-by-token over seconds to minutes. The gateway must:

1. Receive a streaming response from the model provider (SSE)
2. Count tokens in real-time (for quota enforcement)
3. Buffer and scan content for safety (without adding perceptible latency)
4. Forward tokens to the browser as SSE simultaneously
5. Handle hundreds of concurrent streams
6. Gracefully handle provider disconnections, timeouts, and errors mid-stream

This is the most latency-sensitive path in the entire system.

---

## Architecture

```
Browser (EventSource/SSE)
    ▲
    │ SSE: data: {"token": "Hello"}
    │ SSE: data: {"token": " world"}
    │ SSE: data: [DONE]
    │
┌───┴─────────────────────────────────────────────────────────┐
│                    FastAPI SSE Endpoint                       │
│                                                               │
│  1. Validate request (auth, quota pre-check)                  │
│  2. Open async generator pipeline:                            │
│                                                               │
│     Model Provider (SSE stream)                               │
│         │                                                     │
│         ▼                                                     │
│     Token Counter (running total, async)                      │
│         │                                                     │
│         ▼                                                     │
│     Content Safety Buffer (accumulate + scan in chunks)       │
│         │                                                     │
│         ▼                                                     │
│     SSE Serializer → Browser                                  │
│                                                               │
│  3. On stream complete:                                       │
│     - Finalize token count                                    │
│     - Update usage counters (Redis atomic increment)          │
│     - Run full content safety scan on complete response       │
│     - Persist message to database                             │
│     - Write audit log entry                                   │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## Request Lifecycle

### Phase 1: Pre-Flight (before any tokens flow)

```python
async def chat_completion(request: ChatRequest, tenant: TenantContext):
    # 1. Validate the request
    validate_request(request)
    
    # 2. Check quota (can this user make this request?)
    quota_result = await governance.check_quota(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        model_id=request.model,
    )
    if quota_result.denied:
        raise QuotaExceededError(quota_result)
    
    # 3. Estimate cost (based on input tokens + expected output)
    cost_estimate = pricing.estimate(
        model=request.model,
        input_tokens=count_tokens(request.messages),
        estimated_output=request.max_tokens or 4096,
    )
    
    # 4. Run inbound content safety scan
    safety_result = await content_safety.scan_inbound(request.messages)
    if safety_result.blocked:
        raise ContentBlockedError(safety_result)
    
    # 5. Apply DLP (strip PII if detected)
    sanitized_messages = await dlp.scan_and_strip(request.messages)
    
    # 6. Resolve model (apply smart routing, check fallbacks)
    resolved_model = await model_router.resolve(
        requested=request.model,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
    )
    
    # 7. Begin streaming
    return StreamingResponse(
        stream_response(resolved_model, sanitized_messages, tenant, cost_estimate),
        media_type="text/event-stream",
    )
```

### Phase 2: Streaming (tokens flowing)

```python
async def stream_response(model, messages, tenant, cost_estimate):
    token_counter = TokenCounter(model.id)
    content_buffer = ContentBuffer(chunk_size=50)  # scan every ~50 tokens
    full_response = []
    
    try:
        async for chunk in model_router.stream(model, messages):
            # Count tokens
            token_counter.add(chunk)
            
            # Accumulate for safety scanning
            content_buffer.add(chunk.text)
            full_response.append(chunk.text)
            
            # Periodic safety check (every N tokens)
            if content_buffer.ready_for_scan():
                scan_result = await content_safety.scan_partial(content_buffer.text)
                if scan_result.should_halt:
                    # Stop streaming, send error to client
                    yield sse_event({"type": "error", "message": "Content policy violation"})
                    await handle_safety_halt(tenant, scan_result, full_response)
                    return
                content_buffer.reset()
            
            # Forward token to browser
            yield sse_event({
                "type": "token",
                "content": chunk.text,
                "model": model.display_name,
            })
        
        # Stream complete signal
        yield sse_event({"type": "done", "usage": token_counter.summary()})
    
    except ProviderDisconnectError:
        # Model provider dropped the connection
        yield sse_event({"type": "error", "message": "Model provider disconnected"})
        await handle_provider_error(model, tenant)
    
    except ProviderTimeoutError:
        yield sse_event({"type": "error", "message": "Response timed out"})
    
    finally:
        # Phase 3: Post-stream (always runs)
        await finalize_stream(tenant, model, messages, full_response, token_counter)
```

### Phase 3: Post-Stream (after all tokens delivered)

```python
async def finalize_stream(tenant, model, messages, full_response, token_counter):
    complete_text = "".join(full_response)
    
    # 1. Final content safety scan on complete response
    final_safety = await content_safety.scan_outbound(complete_text)
    
    # 2. Calculate actual cost
    actual_cost = pricing.calculate(
        model=model.id,
        input_tokens=token_counter.input_tokens,
        output_tokens=token_counter.output_tokens,
    )
    
    # 3. Update usage counters (atomic Redis operations)
    await governance.record_usage(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        division_id=tenant.division_id,
        department_id=tenant.department_id,
        model_id=model.id,
        provider=model.provider_type,
        input_tokens=token_counter.input_tokens,
        output_tokens=token_counter.output_tokens,
        cost_usd=actual_cost,
    )
    
    # 4. Persist message (unless ephemeral)
    if not conversation.is_ephemeral:
        await messages_repo.create(
            conversation_id=conversation.id,
            role="assistant",
            content=complete_text,
            model_id=model.id,
            input_tokens=token_counter.input_tokens,
            output_tokens=token_counter.output_tokens,
            cost_usd=actual_cost,
            safety_flags=final_safety.flags if final_safety.flagged else None,
        )
    
    # 5. Audit log (always, even for ephemeral — but without content)
    await audit.log(
        org_id=tenant.org_id,
        actor_id=tenant.user_id,
        action="message.assistant_response",
        resource_type="conversation",
        resource_id=conversation.id,
        details={
            "model": model.id,
            "input_tokens": token_counter.input_tokens,
            "output_tokens": token_counter.output_tokens,
            "cost_usd": float(actual_cost),
            "safety_flagged": final_safety.flagged,
            # content NOT included in audit for ephemeral conversations
        },
    )
```

---

## Content Safety During Streaming

The challenge: we want to catch harmful content before it reaches the user, but we can't wait for the entire response before sending tokens.

**Strategy: Two-pass scanning.**

1. **Partial scan (during stream):** Every ~50 tokens, run a lightweight classifier on the accumulated text. This catches obvious violations (slurs, explicit content, PII) with minimal latency. If triggered, halt the stream immediately.

2. **Full scan (post-stream):** After the complete response is assembled, run the full content safety pipeline (toxicity, PII, hallucination indicators, citation verification). If flagged, the message is marked in the database but already delivered to the user. Admin receives an alert.

**Why not scan before delivery?** Buffering the entire response before sending it to the user would add 5-60 seconds of latency. Users would see a spinner instead of streaming tokens. This destroys the UX. The two-pass approach catches critical violations in real-time (partial scan halts on the worst content) while allowing the full scan to run asynchronously on complete responses.

**Configurable strictness:**
- **High (government/K-12):** Larger partial scan buffer (scan every 20 tokens). Higher false positive tolerance. Stream halts more aggressively.
- **Medium (higher ed/enterprise):** Scan every 50 tokens. Balance between safety and UX.
- **Low (research):** Partial scanning disabled. Full post-scan only. Maximum speed.

### Safety Halt UX — What Happens When Content Is Blocked Mid-Stream

This is the hardest UX problem in the streaming pipeline. The user has already seen partial tokens, and now we need to stop and explain why.

**Scenario:** After 150 tokens have streamed to the browser, the partial safety scanner flags the content.

**Protocol:**

1. **Stop streaming immediately.** No more token events.
2. **Send a `safety_halt` event** with structured metadata:

```
data: {"type": "safety_halt", "code": "content_policy", "tokens_delivered": 150, "message": "Response stopped — content policy violation detected.", "category": "toxicity", "action": "halted"}
```

3. **Send `done` event** (the stream is finished, even though incomplete):

```
data: {"type": "done", "usage": {"input_tokens": 200, "output_tokens": 150, "model": "gpt-4o"}, "halted": true}
```

**Frontend behavior on `safety_halt`:**

1. The partially-rendered message gets a visual indicator — a red/amber border or badge.
2. The streamed content is **replaced** with a policy message: *"This response was stopped because it violated the content policy. The partial response has been removed."*
3. The original partial text is **not preserved in the UI** — if the content was harmful enough to halt, it shouldn't remain visible.
4. A "Try again" button appears, allowing the user to regenerate (which may route to a different model or adjust the system prompt).
5. Token usage is still charged — the tokens were consumed even though the response was halted.

**Why replace, not append?** Appending "Content blocked" after harmful content means the harmful content is still on screen. Replacing ensures the user never screenshots or copies the flagged content. The full text is preserved in the audit trail (for compliance review), not in the UI.

**Backend behavior on halt:**

1. Partial response is saved to `messages` table with `safety_flags` populated and a `halted` flag.
2. Full content (pre-halt) is preserved in audit trail — admins can review what triggered the halt.
3. Safety event logged via `log_safety_event` with `direction="outbound"`, `action_taken="halted_stream"`.
4. If the halt category is CSAM or similarly severe, the response is additionally escalated per the incident response controls in `threat-model-controls.md`.

**Post-stream full scan (when partial scan didn't catch it):**

If the partial scanner misses something but the full post-stream scan catches it:

1. The message has already been delivered to the user.
2. The message is **marked in the database** with safety flags.
3. An admin alert is generated (P2 severity — see `observability-slos.md`).
4. The frontend does **not** retroactively remove the message (it's already been seen).
5. The admin can manually review and, if warranted, delete the message and notify the user.

This is the trade-off: we prioritize low latency (stream tokens immediately) at the cost of occasionally delivering content that the full scanner would have caught. The partial scanner handles the obvious cases; the full scanner is the safety net for edge cases.

---

## Concurrent Stream Management

At scale (30,000 users), we may have hundreds or thousands of concurrent streams.

**FastAPI + uvicorn handles this natively.** Each stream is an async generator — it yields tokens, then yields control back to the event loop while waiting for the next token from the provider. There's no thread-per-stream cost. Python's async model handles thousands of concurrent I/O-bound tasks efficiently.

**Connection tracking:**

```python
# Redis-based active stream counter
class StreamManager:
    async def register_stream(self, user_id: str, conversation_id: str):
        key = f"streams:active:{user_id}"
        await redis.sadd(key, conversation_id)
        await redis.expire(key, 3600)  # cleanup after 1 hour
    
    async def unregister_stream(self, user_id: str, conversation_id: str):
        await redis.srem(f"streams:active:{user_id}", conversation_id)
    
    async def active_count(self) -> int:
        # For monitoring/dashboards
        keys = await redis.keys("streams:active:*")
        return sum(await redis.scard(k) for k in keys)
```

---

## SSE Protocol

Messages to the browser follow a consistent format:

```
# Token delivery
data: {"type": "token", "content": "Hello", "model": "GPT-4o"}

# Tool use
data: {"type": "tool_call", "name": "web_search", "args": {"query": "..."}}
data: {"type": "tool_result", "name": "web_search", "content": "..."}

# Metadata updates
data: {"type": "usage", "input_tokens": 150, "output_tokens": 42, "cost": "$0.003"}

# Stream complete
data: {"type": "done", "message_id": "uuid", "usage": {...}}

# Errors
data: {"type": "error", "code": "quota_exceeded", "message": "Daily limit reached"}
data: {"type": "error", "code": "safety_halt", "message": "Content policy violation"}
data: {"type": "error", "code": "provider_error", "message": "Model provider unavailable"}
```

The frontend reconstructs the response from the token stream and handles each event type appropriately.

---

## Timeout and Keepalive

- **Provider timeout:** 120 seconds max for first token. If no token arrives in 120s, the stream fails and the fallback chain is attempted.
- **Idle timeout:** If no token arrives for 30 seconds mid-stream, send a keepalive comment (`:\n\n`) to prevent the browser from closing the connection. If 60 seconds pass with no token, assume provider failure.
- **Max stream duration:** 10 minutes. Any response longer than this is terminated gracefully. This prevents runaway streams from consuming resources indefinitely.
- **Client disconnect detection:** If the browser closes the connection (user navigates away), the server-side generator detects this and cancels the upstream provider request to avoid wasting tokens.
