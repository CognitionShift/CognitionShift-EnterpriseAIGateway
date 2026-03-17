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
- [Testing Strategy](design-docs/testing-strategy.md) — Unit, integration, e2e, load, accessibility, and security testing

### User Documentation
- [User Docs](docs/) — Coming soon

## License

AGPL-3.0 — See [LICENSE](LICENSE) for details.

Commercial licensing available for organizations that need alternative terms. Contact enterprise@cognitionshift.com.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
