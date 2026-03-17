# Operations Documentation

These documents cover the full operational lifecycle of the CognitionShift Enterprise AI Gateway. They are written in **[AEOS (Agent-Executable Operations Specification)](https://github.com/CognitionShift/AEOS)** format — meaning they are both human-readable guides and structured documents that an AI agent can parse and execute step-by-step.

## What is AEOS?

AEOS is a documentation format where every operational step includes:
- **Preconditions** — verifiable checks before the step runs
- **Actions** — the actual commands to execute
- **Verification** — concrete proof that the step succeeded
- **Failure recovery** — specific error patterns mapped to recovery actions

You can follow these docs manually or hand them to an AI agent. Either way, every step is explicit, idempotent, and recoverable.

Learn more: [github.com/CognitionShift/AEOS](https://github.com/CognitionShift/AEOS)

## Documents

| Document | Phase | Description |
|----------|-------|-------------|
| **[install.md](install.md)** | Install | Deploy the gateway from scratch on a single server |
| **[configure.md](configure.md)** | Configure | Post-install setup: models, SSO, content policies, quotas |
| **[operate.md](operate.md)** | Operate | Day-to-day monitoring, health checks, log management, troubleshooting |
| **[update.md](update.md)** | Update | Apply software updates with backup, migration, and rollback |
| **[backup-restore.md](backup-restore.md)** | Backup & Restore | Database backups, file backups, disaster recovery |

## Quick Start

1. Read [install.md](install.md) and follow from top to bottom
2. After install, run through [configure.md](configure.md) to set up models, users, and policies
3. Set up monitoring per [operate.md](operate.md)
4. For updates, follow [update.md](update.md)

## Requirements Summary

- **Server:** 4+ vCPU, 8+ GB RAM, 50+ GB SSD (16 GB RAM recommended)
- **OS:** Ubuntu 22.04+, Amazon Linux 2023, Debian 12+
- **Software:** Docker 24+, Docker Compose 2.20+, Git
- **Network:** Outbound HTTPS to model provider APIs (OpenAI, Anthropic, Google)
- **API Keys:** At least one model provider key (OpenAI, Anthropic, or Google)
