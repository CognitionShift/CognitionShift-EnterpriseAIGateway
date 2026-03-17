# Agent Container Isolation

## Purpose

This document specifies the concrete runtime isolation architecture for agent execution. The threat model (`threat-model-controls.md`) defines *what* we protect against. This document defines *how* — the specific technologies, configurations, and operational procedures.

---

## 1. Decision: gVisor First, Firecracker Optional

**Primary sandbox: gVisor (runsc)**

gVisor intercepts all syscalls in userspace, providing a Linux-compatible kernel interface without exposing the host kernel. It's the right default because:

- **Strong isolation without VM overhead.** gVisor runs as a normal container runtime (OCI-compatible), so it works with standard Kubernetes tooling. No custom AMIs, no nested virtualization.
- **Kubernetes-native.** gVisor integrates as a `RuntimeClass` — agents get gVisor by setting one field in the pod spec. Everything else (networking, storage, scheduling) works normally.
- **Syscall filtering is automatic.** gVisor's Sentry intercepts all syscalls. Dangerous calls (mount, ptrace, bpf, perf_event_open) are denied by default without needing a custom seccomp profile.
- **Battle-tested at scale.** Google runs all Cloud Run and GKE Autopilot workloads in gVisor.

**When to use Firecracker instead:**

Firecracker (microVM) provides hardware-level isolation via KVM. Use it when:
- Customer requires FedRAMP High or DoD IL4+ compliance
- Contract explicitly mandates hypervisor-level isolation
- Air-gapped deployment where the additional operational complexity is acceptable

Firecracker adds ~500ms to container startup (acceptable) but requires KVM-capable hosts and custom node provisioning. We don't make it the default because it limits deployment flexibility.

---

## 2. Container Specification

Every agent container follows this spec:

### 2.1 Base Image

```dockerfile
FROM python:3.12-slim AS agent-base

# Minimal dependencies — no shell, no package manager in final image
RUN pip install --no-cache-dir httpx pydantic structlog \
    && rm -rf /var/lib/apt/lists/* /usr/bin/apt* /usr/bin/dpkg*

# Non-root user
RUN useradd -r -s /bin/false agent
USER agent

# Read-only root filesystem
# /tmp and /workspace are the only writable paths (tmpfs mounts)
WORKDIR /workspace
```

### 2.2 Resource Limits

| Resource | Default | Maximum (Admin Override) | Rationale |
|----------|---------|------------------------|-----------|
| CPU | 1 core | 4 cores | Prevents starving other workloads |
| Memory | 512 MB | 2 GB | OOM-killed if exceeded — no swap |
| Ephemeral storage | 1 GB | 5 GB | /tmp + /workspace combined |
| Network egress | 10 MB/min | 50 MB/min | Prevents data exfiltration |
| Max runtime | 5 min | 30 min | Cost and resource protection |
| Max model API calls | 20 | 100 | Per-execution budget cap |

All limits are enforced by Kubernetes resource requests/limits and custom agent proxy rate limiting.

### 2.3 Pod Spec

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: agent-${RUN_ID}
  namespace: agent-execution
  labels:
    app: cognitionshift-agent
    run-id: ${RUN_ID}
    tenant-id: ${TENANT_ID}
  annotations:
    seccomp.security.alpha.kubernetes.io/pod: runtime/default
spec:
  runtimeClassName: gvisor  # Uses runsc
  
  automountServiceAccountToken: false  # No K8s API access
  enableServiceLinks: false            # No service env vars
  
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  
  containers:
    - name: agent
      image: cognitionshift/agent-runtime:${VERSION}
      
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: [ALL]
      
      resources:
        requests:
          cpu: "500m"
          memory: "256Mi"
        limits:
          cpu: "1000m"
          memory: "512Mi"
          ephemeral-storage: "1Gi"
      
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: workspace
          mountPath: /workspace
      
      env:
        - name: GATEWAY_PROXY_URL
          value: "http://agent-gateway-proxy.agent-execution.svc:8080"
        - name: RUN_ID
          value: "${RUN_ID}"
        - name: AGENT_TOKEN
          valueFrom:
            secretRef:
              name: agent-token-${RUN_ID}
      
      # Liveness: kill if agent hangs
      livenessProbe:
        exec:
          command: ["test", "-f", "/tmp/heartbeat"]
        periodSeconds: 30
        failureThreshold: 2
  
  volumes:
    - name: tmp
      emptyDir:
        medium: Memory  # tmpfs — no disk persistence
        sizeLimit: 256Mi
    - name: workspace
      emptyDir:
        sizeLimit: 1Gi
  
  # Pod-level timeout
  activeDeadlineSeconds: 300  # 5 minutes default
  
  # Auto-cleanup
  restartPolicy: Never
  
  # DNS restriction — only resolve gateway proxy
  dnsPolicy: None
  dnsConfig:
    nameservers:
      - 10.96.0.10  # CoreDNS
    searches:
      - agent-execution.svc.cluster.local
    options:
      - name: ndots
        value: "1"
```

---

## 3. Network Isolation

### 3.1 Network Policy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: agent-isolation
  namespace: agent-execution
spec:
  podSelector:
    matchLabels:
      app: cognitionshift-agent
  
  policyTypes:
    - Ingress
    - Egress
  
  # No ingress — agents don't accept connections
  ingress: []
  
  # Egress: gateway proxy only
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: agent-gateway-proxy
      ports:
        - port: 8080
          protocol: TCP
    
    # DNS resolution (CoreDNS)
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
```

### 3.2 Gateway Proxy

The gateway proxy is the single egress point for all agent traffic. It runs as a sidecar-less service in the `agent-execution` namespace.

```
Agent Container → Gateway Proxy → Gateway Core API → Model Provider
                                                    → Web (if allowed)
                                                    → File Storage
```

**Proxy responsibilities:**
- Authenticate agent requests via per-execution token
- Validate each request against the agent's permission manifest
- Rate-limit outbound requests (model calls, web requests, file access)
- Log every request for audit
- Block any request not in the permission manifest
- Track cumulative egress volume and reject when threshold exceeded

### 3.3 DNS Restriction

Agents use a restricted DNS configuration that only resolves the gateway proxy service name. Any other DNS query returns NXDOMAIN and is logged as a potential bypass attempt.

This is enforced via:
1. Pod-level `dnsPolicy: None` with explicit nameserver config
2. CoreDNS policy that restricts agent namespace queries to approved names
3. gVisor's network stack intercepts DNS at the syscall level

---

## 4. Credential Management

### 4.1 Per-Execution Tokens

Each agent run gets a unique, short-lived token:

```python
@dataclass
class AgentToken:
    run_id: str
    org_id: str
    user_id: str
    permissions: dict          # From agent template permission manifest
    model_budget_tokens: int   # Max tokens this execution can consume
    model_budget_usd: float    # Max cost this execution can consume
    expires_at: datetime       # Absolute expiration (= max runtime)
    
    def to_jwt(self, signing_key: str) -> str:
        """Create a signed JWT for the agent."""
        ...
```

**Token lifecycle:**
1. Orchestrator creates token when provisioning container
2. Token injected as Kubernetes Secret (mounted as env var, not file)
3. Agent includes token in every request to gateway proxy
4. Gateway proxy validates token on every request
5. Token expires when execution timeout is reached
6. Kubernetes Secret deleted when pod is cleaned up

### 4.2 No Long-Lived Secrets

Agents never receive:
- Database credentials
- S3 credentials
- API keys for model providers
- Other agents' tokens
- User session tokens

All external access is mediated by the gateway proxy, which uses its own credentials.

---

## 5. Container Lifecycle

### 5.1 Provisioning

```
1. User requests agent execution via API
2. Orchestrator validates:
   a. User has permission to run this agent template
   b. User's quota allows the estimated cost
   c. Org-level concurrent agent limit not exceeded
3. Orchestrator creates:
   a. Per-execution Kubernetes Secret with agent token
   b. Pod spec from template + resource limits
4. Kubernetes schedules pod on gVisor-capable node
5. Pod starts, agent runtime boots
6. Agent writes /tmp/heartbeat (liveness signal)
7. Agent calls gateway proxy to begin work
```

### 5.2 Monitoring

During execution:
- Liveness probe checks `/tmp/heartbeat` every 30s
- Gateway proxy tracks request volume, token consumption, cost
- Anomaly scorer evaluates syscall denials, network events, resource usage (see `observability-slos.md` Section 4)
- `activeDeadlineSeconds` enforces hard timeout at Kubernetes level

### 5.3 Termination

Normal completion:
```
1. Agent signals completion to gateway proxy
2. Orchestrator collects results
3. Content safety scans results
4. Pod terminated (kubectl delete)
5. Kubernetes Secret deleted
6. Results delivered to user
7. Cost attributed to user/org
```

Kill (admin, timeout, or anomaly):
```
1. Kill signal sent (delete pod with grace period 0)
2. If anomaly-triggered: forensic snapshot first
   a. Pod filesystem diff captured
   b. Network flow logs preserved
   c. Execution trace saved to S3
3. Pod force-deleted
4. Secret deleted
5. User notified with reason
6. Partial results discarded (safety risk)
```

### 5.4 Cleanup

A background job runs every 5 minutes:
- Find pods in `agent-execution` namespace older than their `activeDeadlineSeconds`
- Force-delete any orphaned pods
- Delete associated Kubernetes Secrets
- Log cleanup events to audit trail

---

## 6. Seccomp Profile (Defense in Depth)

Even with gVisor intercepting syscalls, we apply a seccomp profile as a second layer:

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
  "syscalls": [
    {
      "names": [
        "read", "write", "close", "fstat", "lseek", "mmap", "mprotect",
        "munmap", "brk", "rt_sigaction", "rt_sigprocmask", "ioctl",
        "access", "pipe", "select", "sched_yield", "mremap", "msync",
        "mincore", "madvise", "dup", "dup2", "nanosleep", "getpid",
        "sendfile", "socket", "connect", "accept", "sendto", "recvfrom",
        "sendmsg", "recvmsg", "shutdown", "bind", "listen", "getsockname",
        "getpeername", "socketpair", "setsockopt", "getsockopt", "clone",
        "fork", "execve", "exit", "wait4", "kill", "uname", "fcntl",
        "flock", "fsync", "fdatasync", "truncate", "ftruncate",
        "getdents", "getcwd", "chdir", "rename", "mkdir", "rmdir",
        "creat", "link", "unlink", "symlink", "readlink", "chmod",
        "fchmod", "chown", "fchown", "lchown", "umask", "gettimeofday",
        "getrlimit", "getrusage", "sysinfo", "times", "getuid", "getgid",
        "geteuid", "getegid", "setpgid", "getppid", "getpgrp", "setsid",
        "getgroups", "setgroups", "getresuid", "getresgid", "sigaltstack",
        "statfs", "fstatfs", "arch_prctl", "set_tid_address",
        "clock_gettime", "clock_getres", "clock_nanosleep",
        "exit_group", "epoll_wait", "epoll_ctl", "tgkill",
        "openat", "mkdirat", "fchownat", "newfstatat", "unlinkat",
        "renameat", "linkat", "symlinkat", "readlinkat", "fchmodat",
        "faccessat", "pselect6", "ppoll", "set_robust_list",
        "get_robust_list", "epoll_create1", "pipe2", "eventfd2",
        "dup3", "accept4", "timerfd_create", "timerfd_settime",
        "timerfd_gettime", "signalfd4", "getrandom", "memfd_create",
        "statx", "pread64", "pwrite64", "futex", "poll"
      ],
      "action": "SCMP_ACT_ALLOW"
    },
    {
      "names": [
        "mount", "umount2", "ptrace", "bpf", "perf_event_open",
        "unshare", "setns", "pivot_root", "chroot", "reboot",
        "kexec_load", "init_module", "finit_module", "delete_module",
        "kcmp", "keyctl", "request_key", "add_key"
      ],
      "action": "SCMP_ACT_LOG"
    }
  ]
}
```

The `SCMP_ACT_LOG` entries for dangerous syscalls ensure we capture attempted escapes even if gVisor already blocks them. These feed into the anomaly scoring system.

---

## 7. Deployment Requirements

### 7.1 Node Requirements

gVisor nodes need:
- Linux kernel 4.15+ (5.x recommended)
- gVisor installed (`runsc` binary)
- containerd configured with `runsc` runtime
- Kubernetes `RuntimeClass` for gVisor registered

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc
scheduling:
  nodeSelector:
    sandbox-capable: "true"
```

### 7.2 For Firecracker Deployments

Additional requirements:
- KVM-capable hosts (bare metal or nested virt enabled)
- Firecracker binary + jailer
- kata-containers or firecracker-containerd integration
- Separate node pool with `i3` or metal instance types

### 7.3 For Single-Server / Docker Compose

When running without Kubernetes (development/evaluation):
- Agents run in Docker containers with `--security-opt=no-new-privileges`
- Network isolation via Docker network with restricted egress
- Resource limits via Docker `--memory`, `--cpus`, `--pids-limit`
- No gVisor (acceptable for development; document the security gap)

---

## 8. Implementation Phases

### Phase 1: Docker-based isolation (current)
- Agents run in Docker containers (already the deployment model)
- Add network restrictions and resource limits
- Implement gateway proxy for mediated access
- **Target: MVP / pilot deployments**

### Phase 2: gVisor integration
- Deploy gVisor RuntimeClass on EKS
- Migrate agent pods to gVisor runtime
- Add seccomp profiles
- Implement anomaly scoring
- **Target: Production / enterprise customers**

### Phase 3: Firecracker option
- Add Firecracker node pool option
- Implement microVM provisioning
- Document for FedRAMP High customers
- **Target: Government / high-security deployments**

---

## 9. Open Questions

1. **gVisor performance overhead for Python workloads.** gVisor adds ~10-30% overhead for CPU-bound work and higher overhead for I/O-heavy workloads. Since agents primarily make HTTP calls to the gateway proxy (I/O-bound), the overhead should be minimal. Needs benchmarking.

2. **GPU access for code execution agents.** gVisor supports limited GPU passthrough (NVIDIA). If agents need GPU (e.g., running ML inference), this requires additional configuration and weakens isolation. Decision: no GPU in agent containers for v1.

3. **Warm pool for reduced startup latency.** Pre-provisioned agent containers that sit idle could reduce cold-start time from ~3-5s to <1s. Trade-off: resource waste for idle containers. Decision: defer until startup latency becomes a customer complaint.
