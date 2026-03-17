# Observability, SLOs & Alerting Strategy

## Purpose

This document defines the concrete SLOs, key metrics, alerting rules, and security monitoring strategy for CognitionShift Enterprise AI Gateway. It replaces the high-level "we use Grafana" hand-wave with specific numbers, thresholds, and runbook triggers.

---

## 1. Service Level Objectives (SLOs)

### 1.1 Platform SLOs

These are the commitments we make to customers and the thresholds that trigger engineering response.

| SLO | Target | Measurement Window | Burn Rate Alert |
|-----|--------|--------------------|-----------------|
| **Availability** | 99.9% (8.7h downtime/year) | 30-day rolling | >1% error budget consumed in 1 hour |
| **API Latency (non-streaming)** | p50 < 200ms, p95 < 500ms, p99 < 1s | 5-minute window | p95 > 800ms for 10 minutes |
| **Time to First Token (TTFT)** | p50 < 1s, p95 < 3s, p99 < 8s | 5-minute window | p95 > 5s for 10 minutes |
| **Stream Completion Rate** | 99.5% of started streams complete without error | 1-hour rolling | <98% in any 15-minute window |
| **Authentication Latency** | p95 < 300ms (SSO round-trip excluded — gateway processing only) | 5-minute window | p95 > 500ms for 5 minutes |
| **File Upload Processing** | p95 < 30s for files under 10 MB | 1-hour rolling | p95 > 60s |
| **Agent Container Start** | p95 < 15s from request to agent ready | 1-hour rolling | p95 > 30s |
| **Audit Log Delivery** | 100% of events written within 5 seconds of occurrence | Continuous | Any event >30s delayed |

### 1.2 Per-Provider Model SLOs

Tracked per model provider to drive fallback decisions and vendor accountability.

| Metric | Healthy | Degraded (triggers fallback preference) | Critical (triggers circuit breaker) |
|--------|---------|----------------------------------------|-------------------------------------|
| **Error Rate** | <1% | 1–5% | >5% for 2 minutes |
| **p95 TTFT** | <3s | 3–8s | >8s for 5 minutes |
| **p95 Total Latency** | <30s | 30–60s | >60s for 5 minutes |
| **Rate Limit (429) Rate** | <0.5% | 0.5–3% | >3% for 5 minutes |
| **Timeout Rate** | <0.5% | 0.5–2% | >2% for 2 minutes |

These thresholds feed directly into the model router's health scoring from `model-resilience.md`. The passive health tracker uses these exact numbers.

### 1.3 Tenant-Facing SLOs (Customer Dashboard)

Customers see a simplified view in their admin dashboard:

| Metric | Display |
|--------|---------|
| **Platform Uptime** | 30-day rolling percentage with daily breakdown |
| **Request Success Rate** | Their tenant's success rate (excludes user errors like quota exceeded) |
| **Average Response Time** | TTFT average for their tenant's requests |
| **Model Availability** | Per-model availability for models they've enabled |

---

## 2. Key Metrics

### 2.1 Request Pipeline Metrics

Every request through the gateway emits these metrics via OpenTelemetry:

```
# Request lifecycle
gateway.request.count                    {method, endpoint, status_code, tenant_id}
gateway.request.duration_ms              {method, endpoint, status_code, tenant_id}  [histogram]
gateway.request.active                   {tenant_id}  [gauge]

# Model routing
model.request.count                      {provider, model, tenant_id, was_fallback}
model.request.ttft_ms                    {provider, model}  [histogram]
model.request.total_duration_ms          {provider, model}  [histogram]
model.request.tokens_input               {provider, model, tenant_id}  [counter]
model.request.tokens_output              {provider, model, tenant_id}  [counter]
model.request.estimated_cost_usd         {provider, model, tenant_id}  [counter]
model.request.error                      {provider, model, error_type}  [counter]

# Streaming
stream.active                            {provider, model, tenant_id}  [gauge]
stream.completed                         {provider, model, tenant_id, status}  [counter]  # status: success|error|timeout|cancelled
stream.duration_ms                       {provider, model}  [histogram]
stream.tokens_per_second                 {provider, model}  [histogram]
```

### 2.2 Safety & Governance Metrics

```
# Content safety
safety.scan.count                        {direction, action, category}
    # direction: inbound|outbound
    # action: pass|block|redact|warn
    # category: pii|phi|toxicity|injection|csam|dlp_custom
safety.scan.duration_ms                  {direction}  [histogram]
safety.scan.false_positive_reported      {category}  [counter]  # user-reported via feedback

# Specific high-severity events
safety.csam.detected                     {}  [counter]  # ALWAYS alerts
safety.injection.detected               {severity}  [counter]  # severity: low|medium|high|critical
safety.pii.detected                     {pii_type, action}  [counter]

# DLP
dlp.match.count                         {rule_id, action, tenant_id}
dlp.data_volume_scanned_bytes           {direction}  [counter]

# Governance
quota.check.count                       {result, tenant_id}  # result: allowed|soft_cap|throttled|rejected
quota.utilization_pct                   {tenant_id, level}  [gauge]  # level: org|division|dept|team|user
quota.exhaustion.count                  {tenant_id, level}  [counter]  # hard cap hit
budget.remaining_usd                    {tenant_id, level}  [gauge]
budget.projected_exhaustion_days        {tenant_id}  [gauge]  # days until projected budget exhaustion at current rate
```

### 2.3 Resilience Metrics

```
# Fallback
fallback.activation.count               {from_provider, to_provider, reason}
fallback.chain_depth                    {requested_model}  [histogram]  # 1=primary, 2=first fallback, etc.
fallback.all_providers_exhausted        {}  [counter]  # entire chain failed

# Circuit breaker
circuit_breaker.state_change            {provider, from_state, to_state}
circuit_breaker.requests_blocked        {provider}  [counter]

# Retry
retry.attempt.count                     {provider, attempt_number, outcome}
retry.exhausted                         {provider}  [counter]  # all retries failed

# Provider health
provider.health.status                  {provider}  [gauge]  # 0=unreachable, 1=degraded, 2=slow, 3=healthy
provider.health.latency_ms             {provider}  [gauge]  # last health check latency
provider.health.error_rate_pct         {provider}  [gauge]  # sliding window
```

### 2.4 Agent Execution Metrics

```
# Lifecycle
agent.container.started                 {agent_type, tenant_id}
agent.container.completed               {agent_type, tenant_id, exit_status}  # exit_status: success|error|timeout|killed
agent.container.duration_ms             {agent_type}  [histogram]
agent.container.startup_ms              {agent_type}  [histogram]
agent.container.active                  {tenant_id}  [gauge]

# Resource usage
agent.container.cpu_seconds             {agent_type, tenant_id}  [counter]
agent.container.memory_peak_bytes       {agent_type}  [histogram]
agent.container.network_egress_bytes    {agent_type}  [counter]

# Security (critical — feeds into alerting)
agent.proxy.request.count               {agent_id, destination, allowed}
agent.proxy.bypass_attempt              {agent_id, destination_ip, method}  [counter]  # ANY increment = alert
agent.container.escape_indicator        {agent_id, indicator_type}  [counter]  # ANY increment = alert
agent.container.syscall_denied          {agent_id, syscall}  [counter]
agent.container.filesystem_violation    {agent_id, path, operation}  [counter]
```

### 2.5 Infrastructure Metrics

```
# Database
db.connection_pool.active               {service}  [gauge]
db.connection_pool.idle                 {service}  [gauge]
db.connection_pool.waiting              {service}  [gauge]
db.query.duration_ms                    {operation, table}  [histogram]
db.query.slow_count                     {}  [counter]  # >500ms

# Redis
redis.connection.active                 {}  [gauge]
redis.memory_used_bytes                 {}  [gauge]
redis.hit_rate_pct                      {}  [gauge]

# S3
s3.request.count                        {operation, bucket}
s3.request.duration_ms                  {operation, bucket}  [histogram]
s3.request.error                        {operation, bucket, error_type}

# Keycloak
keycloak.auth.count                     {outcome, provider}  # outcome: success|failure|timeout
keycloak.auth.duration_ms               {provider}  [histogram]
keycloak.token.issued                   {}  [counter]
keycloak.token.revoked                  {}  [counter]
```

---

## 3. Alerting Strategy

### 3.1 Severity Levels

| Severity | Response Time | Notification Channel | Examples |
|----------|--------------|---------------------|----------|
| **P0 — Critical** | ≤15 minutes | PagerDuty (wake people up) + Slack #incidents | CSAM detected, container escape indicator, platform down, data breach indicator |
| **P1 — High** | ≤1 hour | PagerDuty (business hours) + Slack #incidents | SLO burn rate critical, all providers for a model down, audit log delivery failure |
| **P2 — Medium** | ≤4 hours (business hours) | Slack #alerts | Single provider degraded, quota exhaustion spike, elevated safety event rate |
| **P3 — Low** | Next business day | Slack #alerts (batched daily digest) | Certificate expiring in 30 days, dependency CVE (non-critical), disk usage >70% |

### 3.2 Alert Rules

#### P0 — Critical (Page Immediately)

```yaml
# Platform availability
- name: platform_down
  condition: probe_success{job="blackbox"} == 0 for 2m
  message: "Platform health check failing for 2+ minutes"
  runbook: runbooks/platform-down.md

- name: error_budget_exhausted
  condition: slo_error_budget_remaining{slo="availability"} < 0
  message: "99.9% availability SLO error budget exhausted"
  runbook: runbooks/slo-breach.md

# Security — container escape
- name: agent_escape_indicator
  condition: increase(agent.container.escape_indicator[5m]) > 0
  message: "SECURITY: Agent container escape indicator detected"
  runbook: runbooks/container-escape.md
  actions:
    - kill_all_agent_containers
    - preserve_forensic_snapshot
    - disable_agent_execution

# Security — proxy bypass
- name: agent_proxy_bypass
  condition: increase(agent.proxy.bypass_attempt[5m]) > 0
  message: "SECURITY: Agent attempted to bypass gateway proxy"
  runbook: runbooks/proxy-bypass.md
  actions:
    - kill_agent_container
    - preserve_forensic_snapshot

# Content safety — CSAM
- name: csam_detected
  condition: increase(safety.csam.detected[1m]) > 0
  message: "CSAM detected — mandatory reporting required"
  runbook: runbooks/csam-response.md
  actions:
    - block_user_session
    - preserve_evidence
    - notify_compliance_officer

# Data integrity — audit failure
- name: audit_log_failure
  condition: increase(audit_log_write_error[5m]) > 0
  message: "Audit log write failures — compliance risk"
  runbook: runbooks/audit-failure.md
  actions:
    - buffer_to_local_disk  # never lose audit events
```

#### P1 — High (Page During Business Hours)

```yaml
# SLO burn rate (fast burn)
- name: availability_slo_fast_burn
  condition: slo_burn_rate{slo="availability", window="1h"} > 14.4
  message: "Availability SLO burning 14x faster than budget allows"
  runbook: runbooks/slo-burn.md

- name: ttft_slo_fast_burn
  condition: histogram_quantile(0.95, model.request.ttft_ms) > 5000 for 10m
  message: "p95 Time to First Token >5s for 10+ minutes"
  runbook: runbooks/ttft-degradation.md

# All providers down for a model
- name: all_providers_exhausted
  condition: increase(fallback.all_providers_exhausted[5m]) > 3
  message: "All providers exhausted for model — users seeing errors"
  runbook: runbooks/all-providers-down.md

# Stream completion rate
- name: stream_completion_low
  condition: rate(stream.completed{status="success"}[15m]) / rate(stream.completed[15m]) < 0.98
  message: "Stream completion rate below 98% — partial responses or errors"
  runbook: runbooks/stream-errors.md

# Authentication failures spike
- name: auth_failure_spike
  condition: rate(keycloak.auth.count{outcome="failure"}[5m]) > 10 * avg_over_time(rate(keycloak.auth.count{outcome="failure"}[5m])[1h:])
  message: "Authentication failure rate 10x above baseline — possible credential stuffing"
  runbook: runbooks/auth-attack.md

# Database connection pool exhaustion
- name: db_pool_exhaustion
  condition: db.connection_pool.waiting > 10 for 5m
  message: "Database connection pool contention — queries queueing"
  runbook: runbooks/db-pool.md
```

#### P2 — Medium (Business Hours, ≤4h)

```yaml
# Single provider degraded
- name: provider_degraded
  condition: provider.health.status < 2 for 5m  # below "slow"
  labels: {provider: "{{$labels.provider}}"}
  message: "Provider {{$labels.provider}} degraded — fallbacks active"
  runbook: runbooks/provider-degraded.md

# Fallback activation rate
- name: fallback_rate_elevated
  condition: rate(fallback.activation.count[1h]) / rate(model.request.count[1h]) > 0.05
  message: "Fallback activation rate >5% — provider reliability issue"

# Safety event rate spike
- name: safety_block_rate_elevated
  condition: rate(safety.scan.count{action="block"}[1h]) > 2 * avg_over_time(rate(safety.scan.count{action="block"}[1h])[7d:])
  message: "Content safety block rate 2x above 7-day average"
  runbook: runbooks/safety-spike.md

# Prompt injection spike
- name: injection_attempts_elevated
  condition: rate(safety.injection.detected{severity=~"high|critical"}[1h]) > 5
  message: "Elevated high/critical prompt injection attempts"
  runbook: runbooks/injection-spike.md

# Quota exhaustion trends
- name: tenant_budget_projected_exhaustion
  condition: budget.projected_exhaustion_days < 7
  labels: {tenant_id: "{{$labels.tenant_id}}"}
  message: "Tenant {{$labels.tenant_id}} projected to exhaust budget in <7 days"

- name: quota_hard_cap_rate
  condition: rate(quota.exhaustion.count[1h]) > 10
  labels: {tenant_id: "{{$labels.tenant_id}}"}
  message: "Tenant {{$labels.tenant_id}} hitting hard quota caps frequently"

# Agent execution
- name: agent_startup_slow
  condition: histogram_quantile(0.95, agent.container.startup_ms) > 30000
  message: "Agent container startup p95 >30s"

# Certificate expiry
- name: cert_expiry_soon
  condition: cert_expiry_days < 14
  message: "TLS certificate expires in <14 days"
```

#### P3 — Low (Daily Digest)

```yaml
- name: dependency_cve_noncritical
  condition: trivy_vulnerability{severity=~"medium|low"} > 0
  message: "Non-critical CVE in dependency — review in next sprint"

- name: disk_usage_warning
  condition: disk_usage_pct > 70
  message: "Disk usage >70% — plan capacity"

- name: cert_expiry_30d
  condition: cert_expiry_days < 30 and cert_expiry_days >= 14
  message: "TLS certificate expires in <30 days"

- name: redis_memory_warning
  condition: redis.memory_used_bytes / redis_memory_max_bytes > 0.7
  message: "Redis memory usage >70%"

- name: slow_query_trend
  condition: rate(db.query.slow_count[1d]) > 1.5 * rate(db.query.slow_count[1d] offset 7d)
  message: "Slow query rate trending upward vs last week"
```

---

## 4. Agent Container Security Monitoring

This is the most security-sensitive observability surface. Agents run user-influenced code in sandboxed containers — monitoring must catch escape attempts, resource abuse, and data exfiltration.

### 4.1 Detection Layers

```
┌─────────────────────────────────────────────────────┐
│              Agent Container Monitoring              │
│                                                      │
│  Layer 1: Network Policy Enforcement (Calico/Cilium) │
│  ├── Only gateway proxy reachable                    │
│  ├── All other egress denied + logged                │
│  └── DNS restricted to gateway service discovery     │
│                                                      │
│  Layer 2: Syscall Filtering (gVisor / seccomp)       │
│  ├── Denied syscalls logged with context             │
│  ├── mount, ptrace, clone3 (with CLONE_NEWUSER),     │
│  │   bpf, perf_event_open → deny + alert             │
│  └── Baseline syscall profile per agent type         │
│                                                      │
│  Layer 3: Gateway Proxy Request Analysis             │
│  ├── All model/web/file requests logged              │
│  ├── Request patterns analyzed for exfiltration      │
│  │   (large outbound data, unusual endpoints)        │
│  └── Per-agent rate limits enforced                  │
│                                                      │
│  Layer 4: Runtime Behavioral Analysis                │
│  ├── CPU/memory usage vs baseline                    │
│  ├── Filesystem access patterns                      │
│  ├── Process tree monitoring                         │
│  └── Anomaly scoring per execution                   │
│                                                      │
│  Layer 5: Post-Execution Forensics                   │
│  ├── Container filesystem diff (what changed)        │
│  ├── Full network flow log preserved                 │
│  └── Execution trace retained for audit              │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 4.2 Container Escape Indicators

These events trigger **immediate P0 alert** and automatic containment:

| Indicator | Detection Method | Automated Response |
|-----------|-----------------|-------------------|
| **Network traffic to non-proxy IP** | Calico/Cilium flow logs — any egress not matching gateway proxy ClusterIP | Kill container, snapshot, disable agent execution for tenant, alert |
| **Privileged syscall attempt** | gVisor/seccomp audit log — `mount`, `ptrace`, `bpf`, `perf_event_open`, `unshare` | Log + increment `escape_indicator`, kill if repeated |
| **Process outside agent runtime** | Process tree monitoring — any process not descended from agent entrypoint | Kill container immediately, snapshot |
| **Filesystem write outside sandbox** | Read-only rootfs + tmpfs monitoring — writes outside `/tmp` and `/workspace` | Block write, log, kill if pattern suggests exploit |
| **Unexpected outbound DNS** | DNS query log — any query not for gateway proxy service name | Block, log, alert |
| **Resource limit breach pattern** | OOM kills + CPU throttle in rapid succession (possible exploit probing) | Kill container after 3 OOM events in 1 minute |
| **Host filesystem access attempt** | Any attempt to read `/proc/1/`, `/sys/`, host mount paths | Kill container, P0 alert |

### 4.3 Proxy Bypass Detection

The gateway proxy is the only authorized egress path for agents. Bypass attempts are detected at multiple layers:

```python
# Layer 1: Network policy (infrastructure level)
# Calico NetworkPolicy denies all egress except gateway proxy
# Denied packets are logged with source pod, destination IP, port

# Layer 2: DNS interception
# Agent containers use a custom DNS resolver that only resolves
# the gateway proxy service name. All other queries return NXDOMAIN
# and are logged as bypass_attempt.

# Layer 3: Gateway proxy request validation
class AgentProxyValidator:
    async def validate_request(self, agent_id: str, request: ProxyRequest):
        # Check: is destination in agent's permission manifest?
        if request.destination not in agent.allowed_destinations:
            metrics.increment("agent.proxy.bypass_attempt", {
                "agent_id": agent_id,
                "destination_ip": request.destination,
                "method": request.method,
            })
            await self.alert_security(agent_id, request)
            return ProxyResponse(status=403, body="Destination not in permission manifest")
        
        # Check: is request volume anomalous? (data exfiltration)
        recent_volume = await self.get_recent_egress_bytes(agent_id, window="5m")
        if recent_volume > agent.max_egress_bytes:
            metrics.increment("agent.proxy.bypass_attempt", {
                "agent_id": agent_id,
                "destination_ip": request.destination,
                "method": "volume_exceeded",
            })
            return ProxyResponse(status=429, body="Egress volume limit exceeded")
        
        # Check: is request pattern consistent with data exfiltration?
        # (e.g., base64-encoded data in query params, suspiciously large POST bodies)
        if self.exfiltration_heuristic(request):
            metrics.increment("agent.proxy.exfiltration_indicator", {
                "agent_id": agent_id,
                "heuristic": "large_encoded_payload",
            })
            # Don't block (could be legitimate), but log and flag for review
            await self.flag_for_review(agent_id, request)
        
        return ProxyResponse(status=200)  # allow
```

### 4.4 Agent Anomaly Scoring

Each agent execution gets a real-time anomaly score (0–100):

| Factor | Weight | Signal |
|--------|--------|--------|
| Denied syscalls | 30 | Count of denied syscalls vs. baseline for agent type |
| Network anomalies | 25 | Blocked egress attempts, unusual DNS queries, volume spikes |
| Resource usage | 15 | CPU/memory vs. p95 baseline for agent type |
| Filesystem anomalies | 15 | Write attempts outside sandbox, unexpected file access patterns |
| Execution duration | 10 | Duration vs. p95 baseline for agent type |
| Process tree | 5 | Unexpected child processes |

**Thresholds:**
- Score 0–30: Normal. No action.
- Score 31–60: Elevated. Log for review. Reduce agent's remaining resource limits.
- Score 61–80: High. Alert P2. Tighten network policies to proxy-only.
- Score 81–100: Critical. Kill container. Alert P1. Preserve forensic data.

---

## 5. Dashboards

### 5.1 Operations Dashboard (NOC View)

Single-screen overview for the on-call engineer:

```
┌──────────────────────────────────────────────────────────────┐
│  PLATFORM STATUS:  ● OPERATIONAL       Uptime: 99.97% (30d) │
├──────────────────┬───────────────────┬───────────────────────┤
│  Active Streams  │  Requests (5m)    │  Error Rate (5m)      │
│     142          │    1,247          │    0.3%               │
├──────────────────┴───────────────────┴───────────────────────┤
│  MODEL PROVIDERS                                             │
│  ● OpenAI     healthy   p95 TTFT: 1.2s   err: 0.1%          │
│  ● Anthropic  healthy   p95 TTFT: 0.9s   err: 0.2%          │
│  ● Google     slow      p95 TTFT: 4.1s   err: 0.8%          │
│  ○ Ollama     offline   (maintenance)                        │
├──────────────────────────────────────────────────────────────┤
│  SAFETY (1h)                                                 │
│  PII blocked: 12  │  Injections: 3  │  DLP matches: 7       │
│  CSAM: 0          │  Toxicity: 18   │  False positive: 2    │
├──────────────────────────────────────────────────────────────┤
│  AGENTS (active)                                             │
│  Running: 8  │  Queued: 2  │  Anomaly score avg: 12         │
│  Escape indicators: 0  │  Proxy bypass attempts: 0          │
├──────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE                                              │
│  DB pool: 23/100  │  Redis: 340MB/2GB  │  S3 req/s: 45      │
│  CPU avg: 34%     │  Memory: 62%       │  Disk: 45%          │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Tenant Admin Dashboard

What institution admins see:

- **Usage summary** — Total requests, tokens, cost this billing period
- **Model breakdown** — Requests per model, average latency, cost per model
- **User activity** — Top users by usage (no conversation content), inactive users
- **Quota status** — Budget utilization at each org level, projected exhaustion
- **Safety events** — Count of blocked/redacted events (no content details), trends
- **Availability** — Platform uptime for their tenant, any incidents affecting them

### 5.3 Security Dashboard

For CognitionShift SOC team:

- **Safety events** — Real-time feed with severity, category, tenant, action taken
- **Agent security** — Active containers, anomaly scores, escape indicators, proxy bypass attempts
- **Authentication** — Failed login heatmap, credential stuffing detection, unusual login patterns
- **Cross-tenant isolation** — Automated test results, any RLS violations caught in testing
- **Provider security** — DPA status, zero-retention verification status, last SOC 2 review date
- **Vulnerability status** — Open CVEs by severity, container image scan results, DAST findings

### 5.4 Cost & Capacity Dashboard

For CognitionShift finance and capacity planning:

- **Revenue vs. cost per tenant** — Margin analysis
- **Model cost trends** — Provider pricing changes, cost per 1K tokens over time
- **Capacity forecast** — At current growth rate, when do we need to scale infra
- **Provider dependency** — % of traffic per provider, concentration risk

---

## 6. Distributed Tracing

Every request gets a trace ID that follows it across all components:

```
Trace: user request → API gateway → auth check → governance check → 
       content safety scan → model router → provider API call → 
       response safety scan → audit log → response delivery
```

### 6.1 Trace Context

```python
# Every request carries trace context
class TraceContext:
    trace_id: str           # W3C trace ID, propagated across all services
    span_id: str            # Current span
    tenant_id: str          # For tenant-scoped filtering
    user_id: str            # For user-scoped debugging (redacted in shared dashboards)
    request_type: str       # chat|completion|embedding|agent|file|admin
    
    # Sensitive fields — visible only to security team
    source_ip: str
    session_id: str
```

### 6.2 Key Spans

| Span Name | Parent | Duration Expectation |
|-----------|--------|---------------------|
| `http.request` | root | Full request lifecycle |
| `auth.validate` | `http.request` | <50ms (token validation) |
| `governance.check` | `http.request` | <10ms (quota + policy) |
| `safety.inbound_scan` | `http.request` | <100ms (DLP + toxicity) |
| `model.route` | `http.request` | <5ms (routing decision) |
| `model.provider_call` | `http.request` | 500ms–60s (model API) |
| `safety.outbound_scan` | `http.request` | <200ms (post-stream) |
| `audit.write` | `http.request` | <50ms (async, non-blocking) |

Traces are sampled at 10% for normal requests, 100% for errors and safety events.

---

## 7. Log Strategy

### 7.1 Log Levels & Retention

| Level | Content | Retention | Storage |
|-------|---------|-----------|---------|
| **SECURITY** | Safety events, auth failures, escape indicators, access violations | 7 years | S3 Object Lock (WORM) |
| **AUDIT** | All user/admin actions, model interactions, file access | 7 years (configurable per tenant) | PostgreSQL + S3 Object Lock |
| **ERROR** | Application errors, provider errors, infrastructure errors | 90 days | CloudWatch / Loki |
| **WARN** | Degraded conditions, approaching limits, retries | 30 days | CloudWatch / Loki |
| **INFO** | Request lifecycle, health checks, normal operations | 14 days | CloudWatch / Loki |
| **DEBUG** | Detailed component behavior (never in production by default) | 3 days (when enabled) | CloudWatch / Loki |

### 7.2 Log Sanitization

**Never log:**
- Prompt content (stored in audit trail, not application logs)
- Model response content
- Authentication tokens or API keys
- PII (even when detected by DLP — log the event, not the data)
- File contents

**Always log:**
- Trace ID, span ID
- Tenant ID, user ID (pseudonymized in shared logs)
- Action taken (block, allow, redact)
- Timing information
- Error codes and categories (not raw error messages from providers that might contain user data)

---

## 8. Runbook Index

Every alert links to a runbook. Runbooks follow a standard template:

```markdown
# Runbook: [Alert Name]

## Severity: P0/P1/P2/P3
## On-Call Response Time: X minutes

## What's happening
[One paragraph explanation]

## Impact
[What users/tenants are affected, what they experience]

## Diagnosis Steps
1. [Check specific dashboard/query]
2. [Check specific logs]
3. [Check specific infrastructure]

## Resolution Steps
1. [Immediate mitigation]
2. [Root cause investigation]
3. [Permanent fix]

## Escalation
- If not resolved in X minutes: escalate to [role]
- If data breach suspected: invoke IR-01

## Post-Incident
- Update this runbook if steps were wrong/incomplete
- File post-incident review
```

**Runbooks to create (tracked in repo as `runbooks/`):**

| Runbook | Alert(s) |
|---------|----------|
| `platform-down.md` | platform_down |
| `slo-breach.md` | error_budget_exhausted |
| `slo-burn.md` | availability_slo_fast_burn, ttft_slo_fast_burn |
| `container-escape.md` | agent_escape_indicator |
| `proxy-bypass.md` | agent_proxy_bypass |
| `csam-response.md` | csam_detected |
| `audit-failure.md` | audit_log_failure |
| `all-providers-down.md` | all_providers_exhausted |
| `stream-errors.md` | stream_completion_low |
| `auth-attack.md` | auth_failure_spike |
| `db-pool.md` | db_pool_exhaustion |
| `provider-degraded.md` | provider_degraded |
| `safety-spike.md` | safety_block_rate_elevated |
| `injection-spike.md` | injection_attempts_elevated |

---

## 9. Implementation Notes

### 9.1 OpenTelemetry Configuration

```python
# FastAPI instrumentation
from opentelemetry import trace, metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# Auto-instrument all the things
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()  # outbound HTTP to model providers

# Custom metrics
meter = metrics.get_meter("cognitionshift.gateway")
model_request_counter = meter.create_counter("model.request.count")
ttft_histogram = meter.create_histogram("model.request.ttft_ms")
safety_scan_counter = meter.create_counter("safety.scan.count")
# ... etc
```

### 9.2 Export Pipeline

```
Application → OpenTelemetry Collector → 
    ├── Metrics → Prometheus → Grafana
    ├── Traces → Tempo → Grafana
    ├── Logs → Loki → Grafana
    └── Security Events → SIEM (customer-specified)
```

Single observability stack (Grafana) for everything. OpenTelemetry Collector as the routing layer means we can add any export destination without changing application code.

### 9.3 Cost of Observability

At 1,000 concurrent users generating ~10 requests/minute each:

| Component | Estimated Volume | Storage (30d) |
|-----------|-----------------|---------------|
| Metrics | ~50K time series | ~2 GB |
| Traces (10% sampling) | ~1M spans/day | ~5 GB |
| Logs | ~10M lines/day | ~10 GB |
| Audit events | ~500K/day | ~3 GB |
| Security events | ~5K/day | ~50 MB |
| **Total** | — | **~20 GB/month** |

Manageable. Grafana Cloud free tier covers this for small deployments. Self-hosted Grafana stack for production.
