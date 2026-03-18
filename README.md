# CognitionShift Enterprise AI Gateway

A deployable enterprise platform that gives organizations secure, governed, model-agnostic access to frontier AI capabilities.

Designed from the ground up for regulated environments — education (FERPA), government (FedRAMP), healthcare (HIPAA), and financial services (SOC 2).

## What Is This?

An **AI operations layer** that sits between your organization's users and the frontier model ecosystem, providing:

- **Governance** — Who can use what, how much, and at what cost
- **Safety** — Content filtering, DLP, prompt injection defense, audit trails
- **Flexibility** — Any model, any provider, including self-hosted
- **Extensibility** — Agentic workflows with sandboxed execution
- **Compliance** — SOC 2, FedRAMP, FERPA, HIPAA, WCAG 2.2 by architecture

## Documentation

### Design Documents
- [Architecture & Design](design-docs/architecture.md) — System architecture, components, deployment model
- [Database Schema](design-docs/database-schema.md) — Multi-tenant data model, all tables, indexes, migration strategy
- [Streaming Architecture](design-docs/streaming-architecture.md) — SSE streaming pipeline, content safety during streaming
- [API Contract](design-docs/api-contract.md) — REST API specification, all endpoints, request/response formats
- [Model Resilience](design-docs/model-resilience.md) — Health checking, fallback chains, circuit breakers, retry logic
- [Caching Strategy](design-docs/caching-strategy.md) — Exact match, semantic, and embedding caches
- [Model Registry](design-docs/model-registry.md) — Institutional AI model catalog, versioning, access controls
- [Testing Strategy](design-docs/testing-strategy.md) — Unit, integration, e2e, load, accessibility, and security testing

### Operations Documentation ([AEOS](https://github.com/CognitionShift/AEOS) format)
- [Install](docs/operations/install.md) — Deploy from scratch on a single server
- [Configure](docs/operations/configure.md) — Models, content safety, quotas, users
- [Operate](docs/operations/operate.md) — Monitoring, health checks, troubleshooting
- [Update](docs/operations/update.md) — Software updates with backup and rollback
- [Backup & Restore](docs/operations/backup-restore.md) — Database backups, disaster recovery

## Quick Start

```bash
git clone https://github.com/CognitionShift/CognitionShift-EnterpriseAIGateway.git
cd CognitionShift-EnterpriseAIGateway
cp .env.example infra/.env
# Edit infra/.env with your domain and API keys
bash infra/generate-env.sh
docker compose -f infra/docker-compose.prod.yml build
docker compose -f infra/docker-compose.prod.yml up -d
```

For the full walkthrough, see [docs/operations/install.md](docs/operations/install.md).

## Configuration & Secrets

⚠️ **Never commit secrets, API keys, passwords, or `.env` files to this repository.**

All sensitive configuration is managed through environment variables. See [`.env.example`](.env.example) for the full list of configuration options with placeholder values. The `.gitignore` excludes `.env` files, but always verify before committing.

For production deployments, see [SECURITY.md](SECURITY.md).

## License

**AGPL-3.0** — See [LICENSE](LICENSE) for details.

### What AGPL-3.0 means for you

- ✅ **Free to use** for internal deployments, evaluation, and development
- ✅ **Free to modify** and deploy within your organization
- ✅ **Free to contribute** improvements back to the project
- ⚠️ **If you modify and distribute** (including offering as a hosted service), you must release your modifications under AGPL-3.0

### Commercial Licensing

For organizations that need terms beyond AGPL-3.0 — including proprietary modifications, OEM embedding, SLA-backed support, or compliance certification assistance — commercial licenses are available.

**Contact:** enterprise@cognitionshift.com

## Security

See [SECURITY.md](SECURITY.md) for our security policy, vulnerability reporting process, and architecture overview.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
