# Caching Strategy

## Current Decision: No Response Caching

Response caching is **not implemented** in v1. This is deliberate.

### Why Not

1. **User experience comes first.** Cached responses are confusing. Users don't understand why they're seeing the same answer they got yesterday, or why "regenerate" seems to do nothing. The cognitive overhead of "is this cached?" is worse than the cost savings.

2. **Non-deterministic by nature.** LLM responses vary even with identical inputs. Caching creates a false sense of consistency that breaks user expectations.

3. **Debugging nightmare.** When something goes wrong, "is it cached?" becomes the first question in every support ticket. Cache invalidation is already one of the two hard problems in computer science — adding it to a multi-tenant AI gateway doesn't make it easier.

4. **Not cost-critical yet.** At launch volumes, the cost of re-generating responses is well within budget. If costs become a problem at scale, we add caching surgically with clear UX indicators.

### What We Do Cache

- **Embedding vectors** — Identical text chunks produce identical embeddings. Caching these in Redis during RAG indexing avoids redundant API calls with zero UX impact. TTL: 7 days.

```python
def embedding_cache_key(text: str, model: str) -> str:
    return f"cache:embed:{model}:{hashlib.sha256(text.encode()).hexdigest()}"
```

- **Model provider health status** — Health check results cached for 30 seconds to avoid hammering provider endpoints.

- **User sessions / auth tokens** — Standard session caching in Redis.

### Future Consideration

If usage data shows a clear pattern of identical high-cost queries (e.g., the same syllabus question asked by 200 students in a class), we may revisit response caching with:
- Explicit opt-in by admins
- Clear UI indicator ("cached response")
- User ability to force a fresh response
- Scoped to temperature=0 only

But that's a v2+ conversation driven by real data, not speculation.
