---
aeos: "0.1"
product: "CognitionShift Enterprise AI Gateway"
version: "0.1.0"
phase: configure
estimated_duration: "15m"
risk_level: low
rollback_strategy: "Restore backend/.env from backup and restart backend"
required_tools:
  - name: docker
    check: "docker --version"
  - name: docker compose
    check: "docker compose version"
  - name: curl
    check: "curl --version"
environment:
  required:
    - name: ADMIN_EMAIL
      description: "Admin account email (created during install)"
      default: "admin@localhost"
    - name: ADMIN_PASSWORD
      description: "Admin account password"
      default: "changeme"
  optional:
    - name: INSTALL_DIR
      description: "Installation directory"
      default: "/opt/csgateway"
---

# Configure — CognitionShift Enterprise AI Gateway

Post-installation configuration. Run this after a successful install to set up model providers, content safety policies, user quotas, and initial users.

> This document follows the [Agent-Executable Operations Specification (AEOS)](https://github.com/CognitionShift/AEOS).

---

## step: Authenticate as Admin

All configuration steps require an admin JWT token. This step obtains one and exports it for subsequent steps.

### preconditions
- run: `curl -sf https://${DOMAIN}/api/v1/health` exits 0
- env: ADMIN_EMAIL is set
- env: ADMIN_PASSWORD is set

### action

```bash
export CSG_TOKEN=$(curl -sf -X POST https://${DOMAIN}/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL:-admin@localhost}\",\"password\":\"${ADMIN_PASSWORD:-changeme}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")

echo "Authenticated. Token: ${CSG_TOKEN:0:20}..."
```

### verify
- env: CSG_TOKEN is set
- run: `curl -sf https://${DOMAIN}/api/v1/auth/me -H "Authorization: Bearer $CSG_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['email'])"` output contains "@"

### on_failure
- pattern: "invalid credentials\|401"
  recovery: "Admin credentials are incorrect. Verify ADMIN_EMAIL and ADMIN_PASSWORD match what was set during install."
  escalate: true
- pattern: "Connection refused"
  recovery: "Backend is not running. Start it: `docker compose -f ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.prod.yml up -d backend`"
  escalate: true

---

## step: Verify Model Providers

Check which model providers are available and responding.

### preconditions
- env: CSG_TOKEN is set

### action

```bash
echo "=== Configured Models ==="
curl -sf https://${DOMAIN}/api/v1/models \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('data', data) if isinstance(data, dict) else data
if not models:
    print('WARNING: No models configured!')
else:
    for m in models:
        name = m.get('display_name', m.get('id', 'unknown'))
        provider = m.get('provider', 'unknown')
        print(f'  {name} ({provider})')
"

echo ""
echo "=== Provider Health ==="
curl -sf https://${DOMAIN}/api/v1/health/detailed \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
providers = data.get('data', {}).get('checks', {}).get('providers', {})
if not providers:
    print('  No provider health data yet')
else:
    for name, healthy in providers.items():
        status = '✓ healthy' if healthy else '✗ unhealthy'
        print(f'  {name}: {status}')
"
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/models -H "Authorization: Bearer $CSG_TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',d)))"` output is >= 1

### on_failure
- pattern: "0\|No models"
  recovery: |
    No models are configured. Add API keys to the environment:
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    # Add your key(s) to backend/.env:
    echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" >> backend/.env
    # Restart backend to pick up new keys:
    docker compose -f infra/docker-compose.prod.yml restart backend
    sleep 10
    ```
  then: retry

---

## step: Configure Content Safety Policy

Set the organization-level content safety rules.

### preconditions
- env: CSG_TOKEN is set
- run: `curl -sf https://${DOMAIN}/api/v1/health` exits 0

### action

```bash
echo "=== Current Content Policy ==="
curl -sf https://${DOMAIN}/api/v1/admin/content-policy \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -m json.tool

echo ""
echo "Setting recommended production content policy..."

curl -sf -X PUT https://${DOMAIN}/api/v1/admin/content-policy \
  -H "Authorization: Bearer $CSG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pii_action": "warn",
    "injection_action": "block",
    "dlp_enabled": true,
    "outbound_scanning": true
  }' | python3 -m json.tool
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/admin/content-policy -H "Authorization: Bearer $CSG_TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',d).get('injection_action','missing'))"` output is "block"

### on_failure
- pattern: "403\|forbidden"
  recovery: "Current user is not an admin. Log in with an admin account."
  escalate: true
- pattern: ".*"
  recovery: "Content policy update failed. Check backend logs."
  escalate: true

---

## step: Configure Quotas

Set default usage quotas for the organization. These can be overridden per-user later.

### preconditions
- env: CSG_TOKEN is set

### action

```bash
echo "=== Current Quotas ==="
curl -sf https://${DOMAIN}/api/v1/admin/quotas \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -m json.tool

echo ""
echo "To create a quota, POST to /api/v1/admin/quotas with:"
echo '  {"scope": "org", "max_tokens_per_day": 1000000, "max_cost_per_day": 50.00, "enforcement": "soft"}'
echo ""
echo "Adjust values based on your organization's budget and expected usage."
echo "Enforcement modes: hard (block), soft (warn), throttle (slow down)"
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/admin/quotas -H "Authorization: Bearer $CSG_TOKEN"` exits 0

### on_failure
- pattern: ".*"
  recovery: "Quota endpoint unreachable. Check backend health."
  escalate: true

---

## step: Create Initial Users

Create user accounts for your team. In production, this would be handled via SSO/SCIM — this step is for initial setup or evaluation.

### preconditions
- env: CSG_TOKEN is set

### action

```bash
echo "=== Current Users ==="
curl -sf https://${DOMAIN}/api/v1/admin/users \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
users = data.get('data', data) if isinstance(data, dict) else data
for u in (users if isinstance(users, list) else []):
    print(f'  {u.get(\"email\", \"?\")} — {u.get(\"role\", \"?\")}')
"

echo ""
echo "To create a user:"
echo '  curl -X POST https://${DOMAIN}/api/v1/auth/register \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '"'"'{"email":"user@example.com","password":"secure-password","name":"Jane Doe"}'"'"''
echo ""
echo "To promote a user to admin (via database):"
echo "  docker exec csgateway-postgres psql -U csgateway -d csgateway \\"
echo "    -c \"UPDATE users SET role='admin' WHERE email='user@example.com'\""
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/admin/users -H "Authorization: Bearer $CSG_TOKEN"` exits 0

---

## step: Configure CORS for Production Domain

If deploying behind a custom domain, update CORS origins.

### preconditions
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/.env exists

### action

<!-- if: $DOMAIN == "localhost" -->
CORS is configured for localhost. No changes needed for development.
<!-- else -->
```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

# Backup current .env
cp backend/.env backend/.env.bak.$(date +%Y%m%d%H%M%S)

# Update CORS origins
sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=[\"https://${DOMAIN}\",\"http://${DOMAIN}:3000\"]|" backend/.env

echo "Updated CORS for domain: ${DOMAIN}"
echo "Restarting backend..."
docker compose -f infra/docker-compose.prod.yml restart backend
sleep 10
```
<!-- endif -->

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/health` exits 0

### on_failure
- pattern: "Connection refused"
  recovery: |
    CORS change may have broken the config. Restore backup:
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    cp backend/.env.bak.* backend/.env 2>/dev/null
    docker compose -f infra/docker-compose.prod.yml restart backend
    sleep 10
    ```
  then: retry
  max_retries: 1

---

## step: Verify Complete Configuration

### preconditions
- step: "Verify Model Providers" completed
- step: "Configure Content Safety Policy" completed

### action

```bash
echo "============================================"
echo "  Configuration Summary"
echo "============================================"
echo ""

# Models
echo "Models:"
curl -sf https://${DOMAIN}/api/v1/models \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('data', data) if isinstance(data, dict) else data
for m in (models if isinstance(models, list) else []):
    print(f'  ✓ {m.get(\"display_name\", m.get(\"id\", \"?\"))}')
" 2>/dev/null || echo "  (unable to list)"

echo ""

# Safety
echo "Content Safety:"
curl -sf https://${DOMAIN}/api/v1/admin/content-policy \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
policy = data.get('data', data)
print(f'  PII: {policy.get(\"pii_action\", \"?\")}')
print(f'  Injection: {policy.get(\"injection_action\", \"?\")}')
print(f'  DLP: {policy.get(\"dlp_enabled\", \"?\")}')
" 2>/dev/null || echo "  (unable to read)"

echo ""

# Users
echo "Users:"
curl -sf https://${DOMAIN}/api/v1/admin/users \
  -H "Authorization: Bearer $CSG_TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
users = data.get('data', data) if isinstance(data, dict) else data
count = len(users) if isinstance(users, list) else 0
print(f'  {count} user(s) registered')
" 2>/dev/null || echo "  (unable to count)"

echo ""
echo "Next: Set up monitoring per operate.md"
echo "============================================"
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/health/detailed | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['status'])"` output is "healthy"
