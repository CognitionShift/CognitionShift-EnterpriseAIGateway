# Caching Strategy

## Why Cache?

Model API calls are expensive — both in latency (500ms-30s) and cost ($0.001-$0.10+ per request). At 30,000 users, identical or near-identical queries will be common. A well-designed caching layer can reduce costs by 15-30% and improve response times dramatically.

---

## Cache Layers

### Layer 1: Exact Match Cache (Redis)

The simplest and most effective cache. If the same user (or any user in the same org) sends the exact same prompt with the same model and system prompt, return the cached response.

**Cache key:**

```python
def cache_key(org_id: str, model_id: str, messages: list, temperature: float) -> str:
    # Deterministic hash of the full request
    payload = json.dumps({
        "org_id": org_id,
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
    }, sort_keys=True)
    return f"cache:exact:{hashlib.sha256(payload.encode()).hexdigest()}"
```

**When to cache:**
- Temperature = 0 (deterministic responses). Always cache.
- Temperature > 0 (stochastic responses). Cache for a short TTL (5 minutes) to debounce rapid re-submissions (user hits "send" twice, page refresh).

**When NOT to cache:**
- Web search or RAG results included (freshness matters)
- Tool use / agent workflows (side effects)
- Ephemeral/zero-retention conversations (nothing persisted)

**TTL:** 24 hours for temperature=0, 5 minutes for temperature>0.

**Storage:** Redis. Cached responses are stored as compressed JSON. A typical response is 2-10KB compressed. At 100K cached responses, that's ~500MB-1GB of Redis — well within capacity.

### Layer 2: Semantic Cache (pgvector)

More advanced: cache responses for queries that are semantically similar, not just identical.

**How it works:**

1. Embed the user's query using the same embedding model as RAG
2. Search the semantic cache for similar queries (cosine similarity > 0.95)
3. If a match is found with the same model and similar system prompt, return the cached response

```python
async def semantic_cache_lookup(org_id, query, model_id, threshold=0.95):
    embedding = await embed(query)
    
    result = await db.execute("""
        SELECT response, 1 - (embedding <=> :embedding) as similarity
        FROM semantic_cache
        WHERE org_id = :org_id
          AND model_id = :model_id
          AND 1 - (embedding <=> :embedding) > :threshold
        ORDER BY embedding <=> :embedding
        LIMIT 1
    """, {"org_id": org_id, "embedding": embedding, 
          "model_id": model_id, "threshold": threshold})
    
    return result.first()
```

**Risks:**
- False positives (similar but meaningfully different queries)
- Stale responses when the user expects fresh reasoning
- Higher complexity than exact cache

**Recommendation:** Implement as opt-in for admins. Start with exact match only for v1. Add semantic caching in v2 after we have real usage data to tune the similarity threshold.

### Layer 3: Embedding Cache (Redis)

Embedding the same document chunk or query twice is pure waste. Cache all embedding operations:

```python
def embedding_cache_key(text: str, model: str) -> str:
    return f"cache:embed:{model}:{hashlib.sha256(text.encode()).hexdigest()}"

async def embed_with_cache(text: str, model: str) -> list[float]:
    key = embedding_cache_key(text, model)
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    
    embedding = await embedding_provider.embed(text, model)
    await redis.set(key, json.dumps(embedding), ex=86400 * 7)  # 7-day TTL
    return embedding
```

This is especially valuable during RAG indexing, where the same document chunks may be re-indexed.

**TTL:** 7 days. Embeddings don't change unless the model changes.

---

## Cache Invalidation

| Event | Action |
|-------|--------|
| Model updated/changed by admin | Invalidate all exact caches for that model |
| Knowledge base re-indexed | Invalidate embedding cache for those documents |
| Content policy changed | Invalidate all caches (responses may now violate new policy) |
| User requests "regenerate" | Bypass cache, generate fresh response |
| Cache TTL expires | Automatic eviction |

---

## Cache Economics

**Example: 30,000 user university deployment**

Assumptions:
- 10,000 active users/day
- 5 queries per user per day = 50,000 queries/day
- Average cost per query: $0.005 (GPT-4o-mini)
- Exact match hit rate: 15% (common questions, syllabus queries, code examples)
- Semantic match hit rate: 10% (additional, if enabled)

**Daily savings:**
- Without cache: 50,000 × $0.005 = $250/day
- With exact cache (15% hit): 42,500 × $0.005 = $212.50/day → **$37.50/day saved**
- With semantic cache (25% total): 37,500 × $0.005 = $187.50/day → **$62.50/day saved**

**Monthly savings: $1,125 - $1,875.** Not transformative but meaningful, and the latency improvement on cache hits (< 50ms vs. 500ms-5s) is immediately noticeable to users.

---

## Cache Transparency

Users should know when they're getting a cached response. The SSE stream includes:

```
data: {"type": "meta", "cached": true, "original_timestamp": "2026-03-16T10:00:00Z"}
```

The UI shows a subtle indicator: "Cached response from earlier today." Users can click "Regenerate" to get a fresh response.

Admins can disable caching globally or per-model via the admin console.

---

## Implementation Priority

1. **v1: Exact match cache** — Simple, safe, significant value. Ship with launch.
2. **v1: Embedding cache** — Essential for RAG performance. Ship with launch.
3. **v2: Semantic cache** — Requires tuning and monitoring. Add after real usage data.
