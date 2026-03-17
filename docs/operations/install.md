---
aeos: "0.1"
product: "CognitionShift Enterprise AI Gateway"
version: "0.1.0"
phase: install
estimated_duration: "25m"
risk_level: low
rollback_strategy: "cd /opt/csgateway && docker compose -f infra/docker-compose.prod.yml down -v"
required_tools:
  - name: docker
    version: ">=24.0"
    check: "docker --version"
  - name: docker compose
    version: ">=2.20"
    check: "docker compose version"
  - name: git
    check: "git --version"
  - name: curl
    check: "curl --version"
required_access:
  - "Server with SSH access and ports 80/443 open"
  - "A domain name pointed at the server (for TLS)"
  - "Internet access for Docker image builds and model API calls"
  - "At least one model provider API key (OpenAI, Anthropic, or Google)"
environment:
  required:
    - name: DOMAIN
      description: "Domain name for the gateway. Caddy auto-provisions TLS via Let's Encrypt."
      example: "gateway.cognitionshift.com"
    - name: ANTHROPIC_API_KEY
      description: "Anthropic API key for Claude models (or set OPENAI_API_KEY or GOOGLE_API_KEY instead)"
      example: "sk-ant-..."
  optional:
    - name: OPENAI_API_KEY
      description: "OpenAI API key for GPT models"
    - name: GOOGLE_API_KEY
      description: "Google AI API key for Gemini models"
    - name: SECRET_KEY
      description: "JWT signing key (random 64-char hex). Auto-generated if not set."
      default: "auto-generated"
    - name: ADMIN_EMAIL
      description: "Initial admin account email"
      default: "admin@localhost"
    - name: ADMIN_PASSWORD
      description: "Initial admin account password"
      default: "changeme"
    - name: INSTALL_DIR
      description: "Installation directory"
      default: "/opt/csgateway"
target_platforms:
  - "Ubuntu 22.04+"
  - "Ubuntu 24.04 LTS (recommended)"
  - "Amazon Linux 2023"
  - "Debian 12+"
minimum_resources:
  cpu: "4 vCPU"
  memory: "8 GB"
  storage: "50 GB SSD"
  recommended:
    cpu: "8 vCPU"
    memory: "16 GB"
    storage: "100 GB SSD"
ports:
  external:
    - "80 (HTTP → HTTPS redirect)"
    - "443 (HTTPS — all traffic)"
  internal_only:
    - "3000 (frontend)"
    - "8000 (backend API)"
    - "5432 (PostgreSQL)"
    - "6379 (Redis)"
---

# Install — CognitionShift Enterprise AI Gateway

> This document follows the [Agent-Executable Operations Specification (AEOS)](https://github.com/CognitionShift/AEOS). Every step includes preconditions, verification, and error recovery — designed for both human operators and AI agents.

**Architecture:** All traffic enters through Caddy on ports 80/443. Caddy handles TLS (auto Let's Encrypt), routes `/api/*` to the backend, and everything else to the frontend. No other ports are exposed.

```
Internet → :443 (Caddy, auto-TLS)
           ├── /api/*  → backend:8000  (internal)
           └── /*      → frontend:3000 (internal)
           
           :80 → 301 redirect to :443
```

---

## step: Verify System Requirements

### preconditions
- platform: linux
- run: `nproc` output is >= 4
- run: `free -g | awk '/^Mem:/{print $2}'` output is >= 7
- run: `df -BG / | awk 'NR==2{print $4}' | tr -d 'G'` output is >= 40

### action

```bash
echo "=== System Requirements Check ==="
echo "CPU cores:  $(nproc)"
echo "Memory:     $(free -h | awk '/^Mem:/{print $2}')"
echo "Disk free:  $(df -h / | awk 'NR==2{print $4}')"
echo "OS:         $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
echo "Kernel:     $(uname -r)"
echo "Arch:       $(uname -m)"
```

### verify
- run: `nproc` output is >= 4
- run: `free -g | awk '/^Mem:/{print $2}'` output is >= 7

### on_failure
- pattern: "output is >= 4"
  recovery: "Minimum 4 CPU cores required."
  escalate: true
- pattern: "output is >= 7"
  recovery: "Minimum 8 GB RAM required (16 GB recommended)."
  escalate: true

---

## step: Verify Ports Available

### preconditions
- platform: linux

### action

```bash
echo "Checking port availability..."
for port in 80 443; do
    if ss -tlnp | grep -q ":${port} "; then
        echo "WARNING: Port ${port} is in use:"
        ss -tlnp | grep ":${port} "
    else
        echo "Port ${port}: available ✓"
    fi
done
```

### verify
- port: 80 is not in use
- port: 443 is not in use

### on_failure
- pattern: "port.*in use"
  recovery: "Ports 80 and 443 must be free. Stop any existing web server (nginx, apache, caddy) before proceeding."
  escalate: true

---

## step: Install Docker

### preconditions
- platform: linux
- run: `which curl` exits 0

### action

<!-- if: `docker --version 2>/dev/null` exits 0 -->
Docker is already installed.
<!-- else -->
```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
newgrp docker || true
```
<!-- endif -->

### verify
- run: `docker --version` exits 0
- run: `docker compose version` exits 0

### on_failure
- pattern: "permission denied"
  recovery: |
    ```bash
    sudo usermod -aG docker $USER && newgrp docker
    ```
  then: retry
- pattern: "Cannot connect to the Docker daemon"
  recovery: |
    ```bash
    sudo systemctl start docker
    ```
  then: retry
- pattern: ".*"
  recovery: "Docker installation failed. Check network connectivity and OS compatibility."
  escalate: true

---

## step: Clone Repository

### preconditions
- run: `git --version` exits 0
- run: `docker --version` exits 0

### action

```bash
INSTALL_DIR="${INSTALL_DIR:-/opt/csgateway}"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Repository exists at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    sudo mkdir -p "$(dirname $INSTALL_DIR)" 2>/dev/null || true
    sudo chown $USER:$USER "$(dirname $INSTALL_DIR)" 2>/dev/null || true
    git clone https://github.com/CognitionShift/CognitionShift-EnterpriseAIGateway.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "Installed at: $(pwd)"
echo "Commit: $(git log --oneline -1)"
```

### verify
- file: ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.prod.yml exists
- file: ${INSTALL_DIR:-/opt/csgateway}/infra/Caddyfile exists
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/Dockerfile exists
- file: ${INSTALL_DIR:-/opt/csgateway}/frontend/Dockerfile.prod exists

### on_failure
- pattern: "Permission denied"
  recovery: |
    ```bash
    sudo chown -R $USER:$USER ${INSTALL_DIR:-/opt/csgateway}
    ```
  then: retry
- pattern: "Repository not found"
  recovery: "Verify the repository URL and access permissions."
  escalate: true

---

## step: Configure Environment

### preconditions
- file: ${INSTALL_DIR:-/opt/csgateway}/infra/.env.example exists
- env: DOMAIN is set

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

# Copy example if no .env exists
if [ ! -f infra/.env ]; then
    cp infra/.env.example infra/.env
fi

# Set values from environment
sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|" infra/.env
sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}|" infra/.env
sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_API_KEY:-}|" infra/.env
sed -i "s|^GOOGLE_API_KEY=.*|GOOGLE_API_KEY=${GOOGLE_API_KEY:-}|" infra/.env

if [ -n "${SECRET_KEY:-}" ]; then
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" infra/.env
fi
if [ -n "${ADMIN_EMAIL:-}" ]; then
    sed -i "s|^ADMIN_EMAIL=.*|ADMIN_EMAIL=${ADMIN_EMAIL}|" infra/.env
fi
if [ -n "${ADMIN_PASSWORD:-}" ]; then
    sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PASSWORD}|" infra/.env
fi

# Generate backend/.env from infra/.env
bash infra/generate-env.sh

chmod 600 infra/.env
echo "Environment configured for: ${DOMAIN}"
```

### verify
- file: ${INSTALL_DIR:-/opt/csgateway}/infra/.env exists
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/.env exists
- run: `grep -c "DOMAIN=" ${INSTALL_DIR:-/opt/csgateway}/infra/.env` output is "1"
- run: `grep -E '^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY)=.+' ${INSTALL_DIR:-/opt/csgateway}/infra/.env | wc -l` output is >= 1
- run: `stat -c %a ${INSTALL_DIR:-/opt/csgateway}/infra/.env` output is "600"

### on_failure
- pattern: "output is >= 1"
  recovery: "No model provider API key set. Export at least one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY"
  escalate: true

---

## step: Build and Start Services

### preconditions
- run: `docker compose version` exits 0
- file: ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.prod.yml exists
- file: ${INSTALL_DIR:-/opt/csgateway}/infra/.env exists
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/.env exists

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

# Load infra env for docker compose
set -a
source infra/.env
set +a

# Build and start everything
docker compose -f infra/docker-compose.prod.yml build --parallel
docker compose -f infra/docker-compose.prod.yml up -d

echo "Waiting for services to start..."
sleep 30

echo ""
echo "=== Service Status ==="
docker compose -f infra/docker-compose.prod.yml ps
```

### verify
- run: `docker ps --filter name=csgateway-caddy --filter status=running -q | wc -l` output is "1"
- run: `docker ps --filter name=csgateway-backend --filter status=running -q | wc -l` output is "1"
- run: `docker ps --filter name=csgateway-frontend --filter status=running -q | wc -l` output is "1"
- run: `docker ps --filter name=csgateway-postgres --filter status=running -q | wc -l` output is "1"
- run: `docker ps --filter name=csgateway-redis --filter status=running -q | wc -l` output is "1"

### on_failure
- pattern: "no space left"
  recovery: |
    ```bash
    docker system prune -f
    ```
  then: retry
- pattern: "port.*already in use"
  recovery: "Port 80 or 443 is in use. Stop the conflicting service."
  escalate: true
- pattern: ".*"
  recovery: |
    Check logs:
    ```bash
    docker compose -f infra/docker-compose.prod.yml logs --tail=30
    ```
  escalate: true

---

## step: Verify Health

### preconditions
- step: "Build and Start Services" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
source infra/.env

# Test via Caddy (the only external path)
echo "=== Testing via HTTPS ==="
curl -sf --max-time 15 "https://${DOMAIN}/api/v1/health" | python3 -m json.tool

echo ""
echo "=== Detailed Health ==="
curl -sf --max-time 15 "https://${DOMAIN}/api/v1/health/detailed" | python3 -m json.tool
```

### verify
- run: `source ${INSTALL_DIR:-/opt/csgateway}/infra/.env && curl -sf "https://${DOMAIN}/api/v1/health" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"` output is "healthy"

### on_failure
- pattern: "Connection refused"
  recovery: "Caddy is not serving. Check: `docker logs csgateway-caddy --tail=20`"
  escalate: true
- pattern: "SSL.*certificate"
  recovery: "TLS certificate not yet provisioned. Verify the domain's DNS A record points to this server's IP, then wait 1-2 minutes for Let's Encrypt."
  then: retry
  max_retries: 3
- pattern: "502"
  recovery: "Caddy is up but backend is not responding. Check: `docker logs csgateway-backend --tail=20`"
  escalate: true

---

## step: Create Admin Account

### preconditions
- step: "Verify Health" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
source infra/.env

ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-changeme}"

echo "Creating admin account: ${ADMIN_EMAIL}"

curl -sf -X POST "https://${DOMAIN}/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${ADMIN_EMAIL}\",
    \"password\": \"${ADMIN_PASSWORD}\",
    \"name\": \"Admin\"
  }" | python3 -m json.tool 2>/dev/null || echo "(account may already exist)"
```

### verify
- run: `source ${INSTALL_DIR:-/opt/csgateway}/infra/.env && curl -sf -X POST "https://${DOMAIN}/api/v1/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"${ADMIN_EMAIL:-admin@localhost}\",\"password\":\"${ADMIN_PASSWORD:-changeme}\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'][:20])"` output is not empty

### on_failure
- pattern: "already exists\|duplicate"
  action: continue
- pattern: "Connection refused"
  recovery: "Backend is not responding. Check: `docker logs csgateway-backend --tail=20`"
  escalate: true

---

## step: Final Verification

### preconditions
- step: "Create Admin Account" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
source infra/.env

echo "============================================"
echo "  CognitionShift Enterprise AI Gateway"
echo "  Installation Complete"
echo "============================================"
echo ""

echo "Health:"
curl -s "https://${DOMAIN}/api/v1/health/detailed" | python3 -m json.tool 2>/dev/null

echo ""
echo "Version:"
curl -s "https://${DOMAIN}/api/v1/system/version" | python3 -m json.tool 2>/dev/null

echo ""
echo "Access:"
echo "  URL:      https://${DOMAIN}"
echo "  API:      https://${DOMAIN}/api/v1/"
echo "  Health:   https://${DOMAIN}/api/v1/health"
echo ""
echo "Admin:"
echo "  Email:    ${ADMIN_EMAIL:-admin@localhost}"
echo "  Password: (as configured)"
echo ""
echo "Exposed Ports:"
echo "  443/tcp — HTTPS (all traffic)"
echo "  80/tcp  — HTTP redirect to HTTPS"
echo "  All other ports are internal only."
echo ""
echo "Next Steps:"
echo "  1. Open https://${DOMAIN} and log in"
echo "  2. Follow configure.md for models, policies, users"
echo "  3. Follow operate.md for monitoring"
echo "============================================"
```

### verify
- run: `source ${INSTALL_DIR:-/opt/csgateway}/infra/.env && curl -sf "https://${DOMAIN}/api/v1/health"` exits 0
- run: `source ${INSTALL_DIR:-/opt/csgateway}/infra/.env && curl -sf "https://${DOMAIN}"` exits 0
- run: `docker compose -f ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.prod.yml ps --format '{{.State}}' | grep -v running | wc -l` output is "0"

### on_failure
- pattern: ".*"
  recovery: "Verification failed. Run: `docker compose -f infra/docker-compose.prod.yml logs --tail=50`"
  escalate: true
