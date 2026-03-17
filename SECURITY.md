# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | ✅ Current release |

As a pre-1.0 project, only the latest release receives security updates.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, report vulnerabilities privately:

- **Email:** security@cognitionshift.com
- **Subject line:** `[SECURITY] Brief description`
- **Include:**
  - Description of the vulnerability
  - Steps to reproduce
  - Affected components (backend, frontend, infrastructure)
  - Severity assessment (if known)
  - Any suggested fix

### Response Timeline

| Stage | Target |
|-------|--------|
| Acknowledgment | Within 48 hours |
| Initial assessment | Within 5 business days |
| Fix or mitigation | Depends on severity (critical: ASAP, high: 7 days, medium: 30 days) |
| Public disclosure | After fix is released, coordinated with reporter |

We follow responsible disclosure. We will not take legal action against researchers who report vulnerabilities in good faith.

## Security Architecture

This platform is designed for regulated environments. Key security features:

- **Multi-tenant isolation** — strict org-level data separation at the database layer
- **Content safety pipeline** — inbound prompt injection defense + outbound content scanning
- **DLP (Data Loss Prevention)** — PII/PHI detection and redaction
- **Audit trail** — append-only, tamper-resistant logging of all user and admin actions
- **Agent sandboxing** — container-isolated execution with gVisor (see [agent-isolation.md](design-docs/agent-isolation.md))
- **Zero-trust credential management** — per-execution tokens, no long-lived secrets in agent containers
- **Encryption** — TLS in transit, AES-256 at rest, tenant-specific KMS keys available

For the full threat model: [threat-model-controls.md](design-docs/threat-model-controls.md)

## Secrets & Configuration

**Never commit secrets, API keys, or credentials to this repository.**

All sensitive configuration is managed via environment variables. See:
- `infra/.env.example` — production environment template
- `docs/operations/install.md` — deployment guide with secret generation

The `.gitignore` excludes `.env` files, but always verify before committing.

## Dependencies

We monitor dependencies for known vulnerabilities. If you discover a vulnerable dependency, please report it via the process above.

## Compliance

This platform targets SOC 2, FedRAMP, FERPA, and HIPAA compliance by architecture. For compliance-specific questions or audit support, contact enterprise@cognitionshift.com.
