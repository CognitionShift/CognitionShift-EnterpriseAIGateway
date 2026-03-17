# Threat Model & Compliance Control Mapping

## Purpose

This document defines the threat model for CognitionShift Enterprise AI Gateway and maps every security control to specific compliance framework requirements. It exists so that during sales, procurement, or certification, we can point to exactly which control satisfies which requirement — no ambiguity, no handwaving.

**This document is the source of truth for security and compliance decisions.** If the architecture doc says one thing and this document says another, update the architecture doc.

---

## 1. Threat Actors

| Actor | Motivation | Capability | Examples |
|-------|-----------|------------|----------|
| **Malicious End User** | Data exfiltration, abuse, circumvention | Authenticated, constrained by role | Student trying to extract another student's data, employee exfiltrating IP |
| **Compromised Account** | Lateral movement, privilege escalation | Valid credentials, appears legitimate | Stolen SSO session, phished credentials |
| **Malicious Administrator** | Data theft, sabotage | Full tenant admin access | Rogue IT admin, insider threat |
| **External Attacker** | Data breach, ransomware, disruption | Network-level, unauthenticated initially | APT, opportunistic scanner, credential stuffing |
| **Compromised Model Provider** | Training data poisoning, response manipulation | Man-in-the-middle on API calls | Compromised API endpoint, malicious model responses |
| **Malicious Agent Code** | Container escape, lateral movement, data exfiltration | Runs inside agent sandbox | User-submitted or compromised agent workflow |
| **Supply Chain Attacker** | Backdoor, dependency compromise | Code-level access via transitive dependency | Compromised PyPI/npm package, malicious container image |
| **CognitionShift Operator** | Unauthorized data access | Infrastructure-level access | Platform operator accessing tenant data (must be prevented by design) |

---

## 2. Attack Surfaces

### 2.1 External Attack Surface

| Surface | Entry Point | Threats |
|---------|------------|---------|
| **Web Application** | HTTPS (443) | XSS, CSRF, session hijacking, authentication bypass |
| **API Endpoints** | HTTPS REST API | Injection, broken auth, BOLA/IDOR, rate limit bypass |
| **SSE Streaming** | HTTPS SSE connections | Connection hijacking, stream injection, resource exhaustion |
| **File Upload** | Multipart POST | Malware, path traversal, zip bombs, polyglot files |
| **Identity Provider** | SAML/OIDC callbacks | SAML assertion replay, XML signature wrapping, token theft |
| **Webhook Endpoints** | HTTPS inbound | SSRF, forged events, replay attacks |

### 2.2 Internal Attack Surface

| Surface | Entry Point | Threats |
|---------|------------|---------|
| **Agent Containers** | Ephemeral pods on EKS | Container escape, resource abuse, network lateral movement |
| **Database** | PostgreSQL connections | SQL injection (mitigated by ORM), privilege escalation, data exfiltration |
| **Redis** | Internal network | Cache poisoning, session manipulation, unauthorized queue access |
| **S3/MinIO** | IAM/network policies | Bucket enumeration, misconfigured ACLs, unencrypted storage |
| **Inter-service Communication** | Internal HTTP/gRPC | Service impersonation, man-in-the-middle |
| **Keycloak Admin** | Admin console | Credential compromise, realm misconfiguration |
| **CI/CD Pipeline** | GitHub Actions | Secret exfiltration, build artifact tampering |

### 2.3 Data Flow Attack Surface

| Flow | Data at Risk | Threats |
|------|-------------|---------|
| **User → Gateway** | Prompts, uploaded files, credentials | Interception, tampering |
| **Gateway → Model Provider** | Prompts + context (may contain PII/PHI) | Provider data retention, interception, provider breach |
| **Gateway → Database** | All persistent data | Query interception, connection hijacking |
| **Gateway → S3** | Files, audit logs | Unauthorized access, tampering |
| **Agent → Gateway Proxy** | Agent requests, tool outputs | Scope bypass, data exfiltration via allowed channels |
| **Gateway → IdP** | Authentication tokens, user attributes | Token theft, attribute manipulation |

---

## 3. STRIDE Analysis — Key Threats

### 3.1 Spoofing

| Threat | Impact | Control |
|--------|--------|---------|
| S1: SSO session replay | Unauthorized access as another user | SAML assertion `NotOnOrAfter` enforcement, one-time-use assertion IDs, session binding to IP/user-agent |
| S2: API key theft | Full API access as stolen identity | API keys hashed (bcrypt) in database, scoped to specific permissions, rotatable, revocable |
| S3: Agent impersonating user | Agent performs actions beyond its scope | Agent credential injection is scoped and ephemeral — credentials destroyed with container. Agents cannot access user sessions. |
| S4: Service impersonation | Internal service-to-service spoofing | mTLS between all internal services, service mesh with identity verification |

### 3.2 Tampering

| Threat | Impact | Control |
|--------|--------|---------|
| T1: Audit log manipulation | Cover tracks after breach | Audit logs are append-only in database, replicated to S3 with write-once policy (S3 Object Lock). Separate IAM role for audit writes — no delete permission. |
| T2: Model response injection | Attacker modifies model output in transit | TLS 1.3 to all model providers, response integrity verified via provider-specific signatures where available |
| T3: Database record modification | Data corruption, privilege escalation | Row-level security (RLS) in PostgreSQL, all mutations via application layer with audit trail, `updated_by` tracked on every write |
| T4: File tampering | Malicious file served to user | Files stored with SHA-256 content hash at upload, verified on every retrieval. S3 versioning enabled. |

### 3.3 Repudiation

| Threat | Impact | Control |
|--------|--------|---------|
| R1: User denies sending prompt | Compliance/legal exposure | Every request logged with user ID, timestamp, source IP, session ID, full request hash. Logs immutable (append-only + S3 Object Lock). |
| R2: Admin denies policy change | Governance failure | All admin actions logged to separate admin audit trail with before/after state |
| R3: Agent action denial | Accountability gap | Every agent action proxied through gateway — full request/response logging per action |

### 3.4 Information Disclosure

| Threat | Impact | Control |
|--------|--------|---------|
| I1: Cross-tenant data leak | Catastrophic — breach of trust | Every database query scoped by `org_id` at ORM level. Row-level security as defense-in-depth. Integration tests verify isolation. |
| I2: PII/PHI in model prompts | FERPA/HIPAA violation | Inbound DLP scanning (pre-model). Configurable: block, strip, or warn. |
| I3: Model training on customer data | Data sovereignty violation | Zero-retention agreements with all model providers. API configurations enforce `training: false` where supported. Data Processing Agreements (DPAs) required. |
| I4: Error message data leakage | Internal details exposed | Structured error responses with sanitized messages. Stack traces never sent to client. Error detail in audit log only. |
| I5: Side-channel via timing/tokens | Usage pattern inference | Token counts are per-user, never exposed cross-tenant. Rate limiting is per-tenant to prevent timing attacks on other tenants' activity. |

### 3.5 Denial of Service

| Threat | Impact | Control |
|--------|--------|---------|
| D1: Streaming connection exhaustion | Platform unavailable | Per-user concurrent stream limit (configurable, default 3). Per-tenant connection pool. WAF rate limiting at ALB layer. |
| D2: Agent resource abuse | Node exhaustion, cost explosion | CPU/memory/time limits per agent container. Network egress rate limiting. Cost circuit breakers halt execution when budget threshold hit. |
| D3: File upload abuse | Storage exhaustion | Per-user and per-org storage quotas. Individual file size limits (configurable, default 100 MB). Rate limiting on upload endpoint. |
| D4: Embedding generation abuse | Compute exhaustion, cost spike | Embedding requests queued with per-tenant priority. Configurable daily embedding token budget. |

### 3.6 Elevation of Privilege

| Threat | Impact | Control |
|--------|--------|---------|
| E1: Role escalation via IdP manipulation | Unauthorized admin access | Role mapping validated against institution-approved role set. Unknown roles default to lowest privilege. Role changes logged and alertable. |
| E2: Agent container escape | Host compromise | Agents run in gVisor/Firecracker micro-VMs (decision pending — see architecture.md remaining decisions). Network policies deny all except gateway proxy. No host mounts. Read-only root filesystem. |
| E3: SQL injection to bypass RLS | Cross-tenant data access | All queries via SQLAlchemy ORM (parameterized). Raw SQL prohibited by linting rules. RLS as defense-in-depth. Penetration testing includes SQLi specifically. |
| E4: BOLA/IDOR on API endpoints | Access to other users' resources | Every API endpoint verifies resource ownership against authenticated user's tenant context. Automated BOLA testing in CI pipeline. |

---

## 4. Compliance Control Mapping

### 4.1 Encryption Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **ENC-01: Data at Rest** | AES-256 encryption for all stored data | PostgreSQL: TDE via RDS encryption (AES-256). S3: SSE-S3 or SSE-KMS (AES-256). Redis: at-rest encryption enabled. EBS volumes: AES-256. | SOC 2 CC6.1, CC6.7 · FedRAMP SC-28 · HIPAA §164.312(a)(2)(iv) · ISO 27001 A.10.1 |
| **ENC-02: Data in Transit** | TLS 1.3 for all network communication | All external traffic: TLS 1.3 (TLS 1.2 minimum, 1.0/1.1 rejected). Internal traffic: mTLS between services. Certificate management via AWS ACM or cert-manager. | SOC 2 CC6.1, CC6.7 · FedRAMP SC-8, SC-13 · HIPAA §164.312(e)(1) · ISO 27001 A.10.1 |
| **ENC-03: Key Management** | Centralized key management with rotation | AWS KMS for encryption keys. Automatic annual rotation. Key usage audited via CloudTrail. Customer-managed keys (CMK) available for tenants that require it. | SOC 2 CC6.1 · FedRAMP SC-12 · HIPAA §164.312(a)(2)(iv) · ISO 27001 A.10.1 |
| **ENC-04: Secrets Management** | No plaintext secrets in code, config, or logs | All secrets in AWS Secrets Manager (or Vault for non-AWS). Secrets injected as environment variables at runtime. Secret values never logged — masked in all output. Rotation enforced on a configurable schedule (default 90 days). | SOC 2 CC6.1 · FedRAMP SC-28(1) · ISO 27001 A.10.1 |
| **ENC-05: Database Connection Encryption** | Encrypted database connections | `sslmode=verify-full` required for all PostgreSQL connections. Client certificates for service accounts. Connection strings never contain plaintext passwords. | SOC 2 CC6.7 · FedRAMP SC-8 · HIPAA §164.312(e)(1) |

### 4.2 Authentication & Authorization Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **AUTH-01: SSO Integration** | Federated authentication via institutional IdP | Keycloak as SAML 2.0 / OIDC broker. No local passwords in production — all authentication delegated to customer IdP. | SOC 2 CC6.1 · FedRAMP IA-2, IA-8 · FERPA (institutional auth) |
| **AUTH-02: MFA Enforcement** | Multi-factor authentication for privileged access | MFA enforced by customer IdP (gateway verifies `amr` claim includes MFA). Platform admin accounts require MFA via Keycloak. API key access: IP allowlisting as compensating control. | SOC 2 CC6.1, CC6.6 · FedRAMP IA-2(1) · HIPAA §164.312(d) |
| **AUTH-03: Session Management** | Secure session lifecycle | JWT access tokens: 15-minute expiry. Refresh tokens: 8-hour expiry, rotated on use, bound to user-agent + IP range. Absolute session timeout: 12 hours (configurable per tenant). Concurrent session limit: configurable (default 5). | SOC 2 CC6.1 · FedRAMP AC-12, SC-23 · HIPAA §164.312(a)(2)(iii) |
| **AUTH-04: API Key Authentication** | Machine-to-machine authentication | API keys: 256-bit random, bcrypt-hashed in database. Scoped to specific permissions and tenant. IP allowlisting optional. Expiration required (max 1 year). Revocable instantly. | SOC 2 CC6.1, CC6.3 · FedRAMP IA-5 |
| **AUTH-05: RBAC + ABAC** | Granular permission model | Role-based access (Admin, Manager, User, Viewer, API-Only) combined with attribute-based policies (department, team, project). Permissions evaluated at every API call — never cached beyond session. Least privilege by default. | SOC 2 CC6.3 · FedRAMP AC-3, AC-6 · FERPA (need-to-know) · HIPAA §164.312(a)(1) |
| **AUTH-06: Provisioning/Deprovisioning** | Automated user lifecycle | SCIM 2.0 for automated provisioning/deprovisioning. Deprovisioned users: session terminated within 5 minutes, access revoked immediately. Data retained per retention policy, then hard-deleted. | SOC 2 CC6.2 · FedRAMP PS-4 · HIPAA §164.312(a)(2)(iii) |

### 4.3 Audit & Logging Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **AUDIT-01: Comprehensive Audit Trail** | All security-relevant events logged | Every API request, authentication event, admin action, policy change, model interaction, file access, and agent action logged with: timestamp (UTC), actor ID, action, resource, source IP, tenant context, outcome (success/failure). | SOC 2 CC7.2, CC7.3 · FedRAMP AU-2, AU-3 · HIPAA §164.312(b) · FERPA (access logging) |
| **AUDIT-02: Audit Log Integrity** | Tamper-proof audit records | Primary: append-only PostgreSQL table (no UPDATE/DELETE grants for application role). Secondary: replicated to S3 with Object Lock (WORM — write once, read many) within 5 minutes. SHA-256 hash chain for integrity verification. | SOC 2 CC7.2 · FedRAMP AU-9 · HIPAA §164.312(b) |
| **AUDIT-03: Audit Retention** | Configurable retention with regulatory minimums | Default retention: **7 years** (exceeds all target framework minimums). Per-tenant configurable within range: 1 year minimum, unlimited maximum. HIPAA: 6 years minimum (we exceed). SOC 2: 1 year minimum (we exceed). FERPA: duration of enrollment + 5 years (we exceed). FedRAMP: 3 years minimum (we exceed). Hard deletion only after retention period + tenant confirmation. | SOC 2 CC7.2 · FedRAMP AU-11 · HIPAA §164.530(j) · FERPA §99.32(a)(1) |
| **AUDIT-04: Log Access Control** | Restricted log access | Audit logs readable only by: platform security team (CognitionShift SOC), tenant admin with explicit audit-viewer role. No regular user access. Log access itself is logged (audit of audit access). | SOC 2 CC7.2 · FedRAMP AU-9 · HIPAA §164.312(b) |
| **AUDIT-05: Security Event Monitoring** | Real-time alerting on suspicious activity | SIEM integration via OpenTelemetry export. Alert rules for: failed auth spikes, privilege escalation attempts, cross-tenant access attempts, content safety violations (CSAM triggers immediate alert), unusual data access patterns. PagerDuty/Slack/email integration. Response SLA: critical alerts ≤ 15 minutes. | SOC 2 CC7.3 · FedRAMP SI-4, IR-6 · HIPAA §164.308(a)(1)(ii)(D) |

### 4.4 Data Protection Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **DATA-01: Tenant Data Isolation** | No cross-tenant data access possible | Row-level security (RLS) in PostgreSQL. `org_id` on every tenant-scoped table, enforced at ORM level + RLS as defense-in-depth. Separate S3 prefixes per tenant. Integration tests specifically verify isolation (cross-tenant queries must return empty). | SOC 2 CC6.1 · FedRAMP AC-4 · HIPAA §164.312(a)(1) · FERPA (institution isolation) |
| **DATA-02: PII/PHI Detection & Protection** | Prevent PII/PHI from reaching model providers unintentionally | Inbound DLP pipeline scans all prompts before model routing. Detects: SSN, credit card, phone, email, medical record numbers, ICD codes, prescription data. Actions per policy: block, strip and replace with `[REDACTED]`, warn user and allow. All detections logged. | SOC 2 CC6.5 · FedRAMP SI-3 · HIPAA §164.312(a)(2)(iv), §164.530(c) · FERPA §99.3 (PII definition) |
| **DATA-03: Data Retention & Deletion** | Enforceable data lifecycle | Per-tenant retention policies (conversations, files, audit logs — separate retention periods). Automated deletion job runs nightly. Hard delete: cryptographic erasure (delete encryption key) for encrypted data, physical deletion + verification for unencrypted. Deletion logged to audit trail. User data export before deletion (GDPR/CCPA portability). | SOC 2 CC6.5 · FedRAMP SI-12 · HIPAA §164.530(j)(2) · FERPA §99.20 (right to amend) |
| **DATA-04: Zero-Retention Model Access** | Customer data not retained by model providers | All model provider agreements require zero-retention (no training, no logging beyond request processing). Verified via: provider API configuration (`training: false`), contractual DPA, annual provider compliance review. Customers can require specific providers or exclude providers based on their data policies. | SOC 2 CC6.1 · FedRAMP SA-9 · HIPAA §164.314(a) (BAA) |
| **DATA-05: Data Residency** | Customer data stored in specified geographic region | Default: US East (us-east-1). Configurable per tenant: US, EU, specific AWS region, or on-premises only. Model routing respects residency — will not send data to providers without regional endpoints matching customer's residency requirement. Residency configuration is immutable once set (requires new tenant to change). | SOC 2 CC6.1 · FedRAMP (US-only for government) · HIPAA (BAA jurisdiction) · GDPR Art. 44-49 |
| **DATA-06: Backup & Recovery** | Data durability and recoverability | Automated daily backups (full) + continuous WAL archiving (point-in-time recovery). Cross-region backup replication. Backup encryption: same KMS key as primary. RPO: < 1 hour. RTO: < 15 minutes (database), < 1 hour (full platform). Backup restoration tested quarterly. Backups subject to same retention policies as source data. | SOC 2 A1.2 · FedRAMP CP-9, CP-10 · HIPAA §164.308(a)(7) |

### 4.5 Network Security Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **NET-01: Perimeter Defense** | Protect against external threats | AWS WAF on ALB: OWASP Top 10 rule set, rate limiting, geo-blocking (configurable). CloudFront for DDoS mitigation. Security groups: deny-all-inbound default, explicit allow for HTTPS only. No public-facing services except ALB. | SOC 2 CC6.6 · FedRAMP SC-7 · HIPAA §164.312(e)(1) |
| **NET-02: Network Segmentation** | Isolate components by function | VPC with private subnets for all backend services. Public subnet only for ALB. Separate subnets for: application tier, database tier, agent execution. Security groups enforce inter-tier communication rules. Agent namespace: deny-all egress except gateway proxy endpoint. | SOC 2 CC6.6 · FedRAMP SC-7(5) · HIPAA §164.312(e)(1) |
| **NET-03: Agent Network Isolation** | Prevent agent lateral movement | Kubernetes NetworkPolicy: agents can only reach gateway proxy service (specific ClusterIP + port). No DNS resolution for internal services. No internet egress. No inter-pod communication. Enforced by Calico/Cilium network policy engine. | SOC 2 CC6.6, CC6.7 · FedRAMP SC-7, AC-4 |
| **NET-04: Internal Communication** | Prevent internal man-in-the-middle | mTLS between all services via service mesh (Istio/Linkerd) or application-level TLS. Certificate rotation automated. No plaintext internal traffic. | SOC 2 CC6.7 · FedRAMP SC-8 |

### 4.6 Incident Response Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **IR-01: Incident Response Plan** | Documented, tested response procedures | Written IRP covering: detection, analysis, containment, eradication, recovery, post-incident review. Roles: Incident Commander, Security Analyst, Communications Lead. Published to all operational staff. | SOC 2 CC7.4, CC7.5 · FedRAMP IR-1, IR-8 · HIPAA §164.308(a)(6) |
| **IR-02: Breach Notification** | Timely notification per regulatory requirements | HIPAA: notify affected individuals within 60 days, HHS if >500 records. FERPA: notify institution (who notifies affected students). GDPR: notify supervisory authority within 72 hours. Contractual: per customer agreement (typically 24-72 hours). All notifications via pre-established secure channel + written follow-up. | HIPAA §164.408 · FERPA §99.33 · FedRAMP IR-6 |
| **IR-03: Forensic Preservation** | Preserve evidence for investigation | On incident detection: automated snapshot of affected resources (DB, logs, containers). Audit logs immutable (cannot be altered by attacker or responder). Chain of custody documented. Forensic copies stored in isolated S3 bucket with separate access controls. | SOC 2 CC7.4 · FedRAMP IR-4 · HIPAA §164.308(a)(6)(ii) |
| **IR-04: Platform Kill Switches** | Immediate containment capability | Per-tenant: disable all access in <1 minute (Keycloak realm disable). Per-model: disable specific provider routing instantly. Per-agent: terminate all running agents for a tenant. Per-user: revoke all sessions immediately via Keycloak admin API. Global: platform-wide read-only mode for catastrophic scenarios. | SOC 2 CC7.4 · FedRAMP IR-4 |

### 4.7 Content Safety Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **CSAFE-01: CSAM Detection & Reporting** | Mandatory detection and law enforcement reporting | PhotoDNA or equivalent hash-matching on all uploaded images. Text-based CSAM indicators flagged by content classifier. **Cannot be disabled by any tenant or admin.** Detection triggers: immediate block, admin alert, evidence preservation, mandatory report to NCMEC CyberTipline within 24 hours. | 18 U.S.C. §2258A (federal mandatory reporting) · SOC 2 CC6.5 |
| **CSAFE-02: DLP / Data Loss Prevention** | Prevent sensitive data exfiltration via AI prompts | Configurable DLP rules per tenant. Built-in patterns: SSN, credit card (Luhn-validated), medical record numbers, ITAR-controlled terminology. Custom regex patterns per tenant. Actions: block, redact, warn. All DLP events logged regardless of action taken. | SOC 2 CC6.5 · FedRAMP SC-7(8) · HIPAA §164.312(a)(2)(iv) |
| **CSAFE-03: Prompt Injection Defense** | Prevent jailbreak and prompt extraction | Multi-layer defense: input validation (encoding, length, structure), known-pattern matching (updated from threat intelligence feeds), LLM-based classifier for novel injection patterns, system prompt isolation (never user-accessible). Detected attempts: blocked + logged + user flagged for review. See **Section 10: Prompt Injection Defense Architecture** for implementation details. | SOC 2 CC6.5 · FedRAMP SI-3, SI-10 |

### 4.8 Availability Controls

| Control | Requirement | Implementation | Frameworks |
|---------|------------|----------------|------------|
| **AVAIL-01: High Availability** | 99.9% platform uptime SLA | Multi-AZ deployment for all stateful services. Auto-scaling for stateless services. Health checks with automatic replacement. Zero-downtime deployments (blue/green). | SOC 2 A1.1, A1.2 · FedRAMP CP-7 |
| **AVAIL-02: Disaster Recovery** | Recovery from regional failure | Cross-region standby (warm). Database replication to standby region. S3 cross-region replication for files and audit logs. Runbook for regional failover. DR test: semi-annually. | SOC 2 A1.2, A1.3 · FedRAMP CP-6, CP-7 · HIPAA §164.308(a)(7) |
| **AVAIL-03: Model Provider Resilience** | Continued operation despite provider outages | Fallback chains (e.g., Claude → GPT-4o → Gemini). Active health checks every 30 seconds. Circuit breakers with automatic failover. Degraded mode: self-hosted model (Llama/Mistral via Ollama) as last resort. User notified when fallback is active. | SOC 2 A1.2 · FedRAMP CP-8 |

---

## 5. Framework-Specific Requirements

### 5.1 HIPAA — Healthcare Deployments

| Requirement | Section | Implementation |
|-------------|---------|----------------|
| **Business Associate Agreement (BAA)** | §164.502(e), §164.314(a) | CognitionShift signs BAA with each healthcare customer. BAA includes: permitted uses/disclosures, safeguard obligations, breach notification terms, subcontractor flow-down. BAA template reviewed by healthcare privacy counsel. |
| **Minimum Necessary** | §164.502(b) | RBAC enforces minimum necessary access. Users see only their conversations and authorized knowledge bases. Admins see usage analytics but not conversation content (unless audit role explicitly granted). |
| **PHI De-identification** | §164.514 | DLP pipeline includes Safe Harbor de-identification (18 HIPAA identifiers). Option for Expert Determination method via configurable rules. De-identification applied before model routing for healthcare tenants. |
| **Audit Controls** | §164.312(b) | See AUDIT-01 through AUDIT-05. HIPAA-specific: access to PHI logged separately with HIPAA-required fields (who, what, when, where, why). |
| **Transmission Security** | §164.312(e)(1) | TLS 1.3 for all external, mTLS for all internal. See ENC-02. |
| **Access Controls** | §164.312(a)(1) | Unique user identification (SSO), emergency access procedure (break-glass admin), automatic logoff (session timeout), encryption (at rest + in transit). |
| **Breach Notification** | §164.408-414 | See IR-02. Automated breach assessment workflow. Notification within 60 days of discovery. HHS notification for breaches affecting 500+ individuals. |

**PHI Data Flow Constraints:**
- Healthcare tenants can restrict model providers to those with signed BAAs (e.g., Azure OpenAI with BAA, not direct OpenAI without BAA)
- PHI-containing prompts: always DLP-scanned, never cached, audit logged with PHI access flag
- Zero-retention enforced — no model provider retains PHI beyond request processing

### 5.2 FERPA — Education Deployments

| Requirement | Section | Implementation |
|-------------|---------|----------------|
| **Legitimate Educational Interest** | §99.31(a)(1) | Access scoped by role. Faculty see only their students' interactions when explicitly granted access (e.g., tutoring review). Students see only their own data. Admins see aggregate analytics, not individual conversations. |
| **Directory Information** | §99.3 | Platform treats all student data as non-directory (most restrictive default). Institutions can configure which fields are directory information per their own policies. |
| **Parental Access Rights** | §99.10 | For K-12 deployments: parent/guardian role with read access to minor's conversations. For higher ed: student controls access (age 18+ / enrolled in post-secondary). |
| **Right to Inspect & Amend** | §99.20 | Students/parents can export all their data (conversations, files, usage). Amendment requests handled via admin workflow — original preserved in audit trail, amendment noted. |
| **Disclosure Logging** | §99.32 | Every disclosure of student education records logged: recipient, date, purpose, specific records disclosed. Maintained for life of record + 5 years. |
| **Data Sharing** | §99.33 | Third-party model providers: DPA required, zero-retention, educational-purpose-only use. No re-disclosure to sub-processors without matching DPA. Annual compliance review of all model providers. |

**Education-Specific Features:**
- Course-scoped knowledge bases (instructor controls content per course)
- Academic integrity metadata (timestamps, interaction logs exportable per institution policy)
- Student data never used for marketing, profiling, or non-educational purposes
- COPPA compliance for K-12: parental consent workflow for users under 13

### 5.3 FedRAMP — Government Deployments

| Requirement | Control Family | Implementation |
|-------------|---------------|----------------|
| **Access Control** | AC-1 through AC-25 | RBAC + ABAC, session management, MFA, least privilege. See AUTH-01 through AUTH-06. |
| **Audit & Accountability** | AU-1 through AU-16 | Comprehensive logging, tamper-proof storage, retention, monitoring. See AUDIT-01 through AUDIT-05. |
| **Configuration Management** | CM-1 through CM-11 | Infrastructure as Code (Terraform), immutable deployments, no manual changes to production. Configuration baseline documented. Change management via PR review + approval. |
| **Identification & Authentication** | IA-1 through IA-11 | Federal PKI / PIV card support via Keycloak. See AUTH-01, AUTH-02. |
| **Incident Response** | IR-1 through IR-10 | See IR-01 through IR-04. US-CERT reporting within 1 hour for federal systems. |
| **System & Communications Protection** | SC-1 through SC-39 | Encryption, network segmentation, WAF, DDoS mitigation. See ENC and NET controls. |
| **System & Information Integrity** | SI-1 through SI-16 | Content safety scanning, malware detection, vulnerability scanning, patch management. |
| **Personnel Security** | PS-1 through PS-8 | Background checks for all CognitionShift staff with access to FedRAMP environments. Separation of duties. |
| **Physical & Environmental** | PE-1 through PE-20 | Inherited from AWS (FedRAMP-authorized IaaS). Documented in SSP. |

**FedRAMP-Specific Architecture:**
- Deployment in AWS GovCloud (us-gov-west-1) for Moderate/High
- FIPS 140-2 validated cryptographic modules (AWS CloudHSM option)
- Continuous monitoring: monthly vulnerability scans, annual penetration test, daily automated compliance checks
- POA&M tracking for all findings
- ConMon reporting: monthly to 3PAO, annually to FedRAMP PMO

### 5.4 SOC 2 — Trust Services Criteria

| Trust Service Category | Key Controls | Implementation |
|------------------------|-------------|----------------|
| **CC6: Logical & Physical Access** | CC6.1-CC6.8 | Encryption, authentication, authorization, network security. See ENC, AUTH, NET controls. |
| **CC7: System Operations** | CC7.1-CC7.5 | Monitoring, incident detection, incident response. See AUDIT-05, IR-01 through IR-04. |
| **CC8: Change Management** | CC8.1 | Git-based change management. All changes via PR with review. CI/CD enforces: linting, tests, security scanning, approval. No direct production access. |
| **CC9: Risk Mitigation** | CC9.1-CC9.2 | This threat model. Risk register maintained and reviewed quarterly. Vendor risk assessments for all model providers and sub-processors. |
| **A1: Availability** | A1.1-A1.3 | See AVAIL-01 through AVAIL-03. SLA monitoring. |
| **C1: Confidentiality** | C1.1-C1.2 | Tenant isolation, encryption, DLP, access controls. See DATA-01 through DATA-06. |
| **P1: Privacy** (if applicable) | P1.1-P1.8 | Privacy notice, consent management, data minimization, access rights, deletion rights. Configurable per regulatory requirement. |

---

## 6. Vendor / Sub-Processor Risk

Model providers are sub-processors handling customer data. Each must meet:

| Requirement | Details |
|-------------|---------|
| **Data Processing Agreement (DPA)** | Signed before provider is enabled. Covers: data handling, retention, breach notification, audit rights, sub-processor restrictions. |
| **Zero-Retention Verification** | API-level enforcement where supported. Contractual guarantee where not. Annual verification via provider SOC 2 report review. |
| **BAA (for HIPAA tenants)** | Provider must sign BAA before healthcare tenant traffic is routed. Providers without BAA: blocked for HIPAA tenants. |
| **SOC 2 Report Review** | Annual review of each provider's SOC 2 Type II. Exceptions reviewed by security team and documented. |
| **Incident Notification** | Provider must notify CognitionShift within 24 hours of any security incident affecting our data. |

**Current Provider Assessment Status:**

| Provider | DPA | Zero-Retention | BAA Available | SOC 2 | Notes |
|----------|-----|---------------|---------------|-------|-------|
| OpenAI | ✅ Available | ✅ API option | ✅ Via Azure | ✅ Type II | Direct API = no BAA. Azure OpenAI = BAA available. |
| Anthropic | ✅ Available | ✅ Default | ⚠️ Contact sales | ✅ Type II | Commercial API default zero-retention. |
| Google (Vertex AI) | ✅ Available | ✅ Default | ✅ Available | ✅ Type II | GCP Vertex AI — full enterprise compliance. |
| AWS Bedrock | ✅ Inherited | ✅ Default | ✅ AWS BAA | ✅ Type II | Best path for FedRAMP workloads. |
| Self-Hosted (vLLM/Ollama) | N/A | N/A (no third party) | N/A | N/A | Customer controls everything. Required for air-gap. |

---

## 7. Security Testing & Validation

| Activity | Frequency | Scope | Standard |
|----------|-----------|-------|----------|
| **SAST (Static Analysis)** | Every PR | All application code | Bandit (Python), ESLint security rules (JS/TS) |
| **SCA (Dependency Scanning)** | Daily + every PR | All dependencies | Dependabot / Snyk, CVE database |
| **DAST (Dynamic Analysis)** | Weekly (staging) | All API endpoints + web UI | OWASP ZAP automated scan |
| **Container Image Scanning** | Every build | All Docker images | Trivy — critical/high CVEs block deployment |
| **Penetration Testing** | Annually + after major changes | Full platform | Third-party firm, OWASP Testing Guide methodology |
| **BOLA/IDOR Testing** | Every PR (automated) | All API endpoints | Custom test suite verifying cross-tenant isolation |
| **Vulnerability Disclosure** | Ongoing | External reporters | security@cognitionshift.com, responsible disclosure policy published |
| **Red Team Exercise** | Annually | Full platform + social engineering | External red team, includes phishing and insider threat scenarios |
| **DR Test** | Semi-annually | Full failover and recovery | Documented runbook execution, measured RTO/RPO |

---

## 8. Compliance Document Inventory

Documents required for sales, procurement, and certification:

| Document | Status | Owner | Update Frequency |
|----------|--------|-------|-----------------|
| **This Threat Model** | ✅ Draft | Security Lead | Quarterly + after architecture changes |
| **SOC 2 Type II Report** | ✅ Existing (Data Machines) | External auditor | Annual |
| **HECVAT Full** | 🔲 To complete | Security Lead | Per-deployment |
| **VPAT (WCAG 2.2 AA)** | 🔲 To complete | Accessibility Lead | Per-release |
| **System Security Plan (SSP)** | 🔲 Required for FedRAMP | Security Lead | Annual |
| **Incident Response Plan** | 🔲 To formalize | Security Lead | Annual |
| **Business Continuity Plan** | 🔲 To formalize | Operations Lead | Annual |
| **Data Processing Agreement (template)** | 🔲 To draft | Legal | As needed |
| **BAA Template** | 🔲 To draft (for HIPAA customers) | Legal | As needed |
| **Privacy Policy** | 🔲 To draft | Legal | Annual |
| **Responsible Disclosure Policy** | 🔲 To publish | Security Lead | Annual |
| **Vendor Risk Assessment Template** | 🔲 To create | Security Lead | Per-vendor |

---

## 9. Open Decisions

These security decisions are identified but not yet finalized:

1. **Agent Sandboxing Technology** — Firecracker (strongest isolation, more operational complexity) vs. gVisor (good isolation, simpler operations) vs. Kubernetes pod security (weakest, simplest). Recommendation: gVisor for initial release, Firecracker option for FedRAMP/high-security.

2. **Content Safety Provider** — Build in-house (more control, slower) vs. integrate third-party (Azure AI Content Safety, Perspective API). Sub-processor implications for third-party. Recommendation: Azure AI Content Safety for initial release (Microsoft BAA covers it), with option to swap to self-hosted classifiers for air-gap.

3. **FIPS 140-2 Compliance** — Required for FedRAMP Moderate+. AWS provides FIPS endpoints. Application-level crypto must use FIPS-validated modules. Decision: use AWS CloudHSM for key management in FedRAMP deployments, standard KMS elsewhere.

4. **Log Shipping Destination** — CloudWatch (AWS-native, simple) vs. self-hosted ELK/Loki (portable, more control) vs. both. Decision: OpenTelemetry export allows multiple backends — ship to CloudWatch for AWS deployments, customer-specified SIEM for enterprise.

---

## 10. Prompt Injection Defense Architecture

Prompt injection is the most active attack vector against AI gateways. Regex pattern matching (our current implementation) catches known patterns but fails against novel attacks, encoding tricks, and multilingual injection. This section specifies the layered defense.

### 10.1 Defense Layers

```
User Input
    │
    ▼
Layer 1: Input Validation & Normalization
    │  • Unicode normalization (NFC)
    │  • Strip invisible characters (zero-width spaces, RTL overrides)
    │  • Decode nested encodings (base64, hex, URL-encoded within prompt)
    │  • Enforce max input length (configurable, default 32K chars)
    │  • Reject binary content in text fields
    │
    ▼
Layer 2: Known Pattern Matching (Fast, Synchronous)
    │  • Regex patterns for known injection phrases (current implementation)
    │  • Updated from threat intelligence feeds (OWASP LLM Top 10, HackerOne reports)
    │  • Token-level pattern matching (catches obfuscation like "ig.nore prev.ious")
    │  • Multilingual patterns (common injections translated to top 10 languages)
    │  • Latency budget: <5ms
    │
    ▼
Layer 3: Structural Analysis (Fast, Synchronous)
    │  • Detect role-boundary injection (user text containing system/assistant markers)
    │  • Detect prompt-template injection (Jinja/f-string/mustache syntax)
    │  • Detect XML/JSON/YAML structure injection
    │  • Detect excessive repetition (token-bombing / context exhaustion)
    │  • Latency budget: <10ms
    │
    ▼
Layer 4: ML Classifier (Async, Optional)
    │  • Lightweight classifier trained on injection/benign corpus
    │  • Options:
    │    a. Self-hosted: Fine-tuned BERT/DeBERTa (~50M params, <100ms on CPU)
    │    b. Third-party: Azure AI Content Safety prompt shields
    │    c. LLM-as-judge: Ask a fast model "Is this a prompt injection?" (expensive, ~500ms)
    │  • Returns confidence score (0.0–1.0)
    │  • Latency budget: <200ms (async, doesn't block if layer 1-3 passed)
    │
    ▼
Layer 5: System Prompt Isolation
       • System prompts are NEVER included in user-visible context
       • System prompts are injected server-side, not via API
       • The model sees system/user/assistant roles; user cannot set system role
       • Output never includes system prompt content (output scanner checks for leakage)
```

### 10.2 Action Matrix

| Layer | Confidence | Action |
|-------|-----------|--------|
| Layer 2: Known pattern | Match | Block immediately. Log. Flag user. |
| Layer 3: Structural | High confidence injection markers | Block. Log. |
| Layer 3: Structural | Suspicious but ambiguous | Add `[INJECTION_WARNING]` flag to audit, allow through. |
| Layer 4: ML classifier | Score ≥ 0.9 | Block. Log. Flag user for review. |
| Layer 4: ML classifier | Score 0.7–0.9 | Allow but: add safety prefix to system prompt, log with warning, increase outbound scan sensitivity. |
| Layer 4: ML classifier | Score < 0.7 | Allow normally. |
| Layer 5: Output leak | System prompt detected in output | Strip from output. Log. Alert admin. |

### 10.3 System Prompt Protection

The system prompt is the highest-value target for injection attacks. Protection:

1. **Server-side injection only.** The system prompt is prepended by the gateway, never passed by the client. The API accepts `system_prompt_override` only for admin-level users.

2. **Output scanning for leakage.** The outbound safety scanner checks if the model's response contains the system prompt (or significant substrings). If detected, the response is modified to remove the leaked content.

3. **Canary tokens.** Each system prompt includes a unique, random canary string. If the canary appears in the model output, it proves the model was tricked into revealing the system prompt.

```python
CANARY_PREFIX = "CSG-CANARY-"

def inject_canary(system_prompt: str) -> tuple[str, str]:
    """Add canary token to system prompt. Returns (modified_prompt, canary)."""
    canary = f"{CANARY_PREFIX}{secrets.token_hex(8)}"
    modified = f"{system_prompt}\n\n[Internal reference: {canary}]"
    return modified, canary

def check_canary_leak(output: str, canary: str) -> bool:
    """Check if canary token leaked into model output."""
    return canary in output or CANARY_PREFIX in output
```

### 10.4 Encoding Attack Prevention

Attackers encode injection payloads to bypass regex:
- Base64: `aWdub3JlIHByZXZpb3VzIGluc3RydWN0aW9ucw==`
- Hex: `\x69\x67\x6e\x6f\x72\x65`
- Unicode confusables: `іgnоre` (Cyrillic і and о look identical to Latin)
- Zero-width characters: invisible characters between letters
- ROT13, pig latin, reversed text

**Mitigation:** Layer 1 normalizes all text before any other scanning:

```python
import unicodedata

def normalize_for_scanning(text: str) -> str:
    """Normalize text to catch encoding-based evasion."""
    # Unicode NFC normalization
    text = unicodedata.normalize("NFC", text)
    
    # Strip zero-width and invisible characters
    text = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]', '', text)
    
    # Normalize confusable characters (Cyrillic→Latin, etc.)
    # Uses Unicode confusables.txt mapping
    text = normalize_confusables(text)
    
    # Detect and decode embedded base64
    base64_pattern = re.compile(r'[A-Za-z0-9+/]{20,}={0,2}')
    for match in base64_pattern.finditer(text):
        try:
            decoded = base64.b64decode(match.group()).decode('utf-8', errors='ignore')
            if any(kw in decoded.lower() for kw in ['ignore', 'system', 'instruction', 'override']):
                text = text.replace(match.group(), decoded)
        except Exception:
            pass
    
    return text
```

### 10.5 Metrics & Feedback Loop

```
# Injection detection metrics (feed into observability-slos.md alerts)
safety.injection.detected               {layer, severity, action}
safety.injection.false_positive_reported {layer}
safety.injection.encoding_evasion       {encoding_type}
safety.system_prompt_leak.detected      {}
safety.canary_leak.detected             {}
```

False positive reports (user clicks "this isn't an injection") feed back into the ML classifier training pipeline. High false-positive rates on specific patterns trigger review and threshold adjustment.

### 10.6 Limitations & Honest Assessment

No prompt injection defense is 100% effective. LLMs are instruction-following machines by design — telling them to ignore instructions is always going to be an arms race.

**What we can guarantee:**
- Known attack patterns are blocked
- Encoding evasion is mitigated by normalization
- System prompts are protected by canary tokens and output scanning
- All attempts are logged for forensic review

**What we cannot guarantee:**
- Novel injection techniques not in our pattern database
- Semantic injection that reads like normal conversation
- Attacks that exploit model-specific training artifacts

**Our strategy:** Defense in depth. No single layer needs to be perfect. The combination of normalization + pattern matching + structural analysis + ML classification + output scanning catches the vast majority of attacks. The rest is caught by the audit trail and admin review.
