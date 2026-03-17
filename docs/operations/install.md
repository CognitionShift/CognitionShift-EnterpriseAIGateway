---
aeos: "0.1"
product: "CognitionShift Enterprise AI Gateway"
version: "0.1.0"
phase: install
estimated_duration: "25m"
risk_level: low
rollback_strategy: "cd /opt/csgateway && docker compose -f infra/docker-compose.dev.yml down -v"
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
  - "Target server with SSH access"
  - "Internet access for Docker image builds and model API calls"
  - "At least one model provider API key (OpenAI, Anthropic, or Google)"
environment:
  required:
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
    - name: DOMAIN
      description: "Domain name for the gateway. Used for CORS and TLS."
      default: "localhost"
    - name: FRONTEND_URL
      description: "URL where the frontend is accessible"
      default: "http://localhost:3000"
    - name: INSTALL_DIR
      description: "Installation directory"
      default: "/opt/csgateway"
target_platforms:
  - "Ubuntu 22.04+"
  - "Ubuntu 24.04 LTS (recommended)"
  - "Amazon Linux 2023"
  - "Debian 12+"
  - "macOS 14+ (development only)"
minimum_resources:
  cpu: "4 vCPU"
  memory: "8 GB"
  storage: "50 GB SSD"
  recommended:
    cpu: "8 vCPU"
    memory: "16 GB"
    storage: "100 GB SSD"
---

# Install — CognitionShift Enterprise AI Gateway

> This document follows the [Agent-Executable Operations Specification (AEOS)](https://github.com/CognitionShift/AEOS). Every step includes preconditions, verification, and error recovery — designed for both human operators and AI agents.

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
  recovery: "Minimum 4 CPU cores required. Current server does not meet requirements."
  escalate: true
- pattern: "output is >= 7"
  recovery: "Minimum 8 GB RAM required (16 GB recommended). Current server does not meet requirements."
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
- run: `docker info --format '{{.ServerVersion}}'` output is not empty

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
    echo "Repository already exists at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    sudo mkdir -p "$(dirname $INSTALL_DIR)"
    sudo chown $USER:$USER "$(dirname $INSTALL_DIR)"
    git clone https://github.com/CognitionShift/CognitionShift-EnterpriseAIGateway.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "Installed at: $(pwd)"
echo "Commit: $(git log --oneline -1)"
```

### verify
- file: ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.dev.yml exists
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/app/main.py exists
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/Dockerfile exists

### on_failure
- pattern: "Permission denied"
  recovery: |
    ```bash
    sudo chown -R $USER:$USER ${INSTALL_DIR:-/opt/csgateway}
    ```
  then: retry
- pattern: "Repository not found"
  recovery: "Verify the repository URL and your access permissions."
  escalate: true

---

## step: Generate Environment Configuration

### preconditions
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/app/config.py exists

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
DOMAIN="${DOMAIN:-localhost}"
FRONTEND_URL="${FRONTEND_URL:-http://${DOMAIN}:3000}"

cat > backend/.env << EOF
# CognitionShift Enterprise AI Gateway
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)

# Environment
DEBUG=false
ENVIRONMENT=production

# Security
SECRET_KEY=${SECRET_KEY}

# Database (internal Docker network)
DATABASE_URL=postgresql+asyncpg://csgateway:csgateway@postgres:5432/csgateway

# Redis (internal Docker network)
REDIS_URL=redis://redis:6379/0

# CORS
CORS_ORIGINS=["${FRONTEND_URL}"]

# Model Providers — at least one required
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
GOOGLE_API_KEY=${GOOGLE_API_KEY:-}
EOF

chmod 600 backend/.env
echo "Environment file written to backend/.env"
```

### verify
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/.env exists
- run: `grep -c SECRET_KEY ${INSTALL_DIR:-/opt/csgateway}/backend/.env` output is "1"
- run: `grep -c DATABASE_URL ${INSTALL_DIR:-/opt/csgateway}/backend/.env` output is "1"
- run: `stat -c %a ${INSTALL_DIR:-/opt/csgateway}/backend/.env` output is "600"
- run: `grep -E '^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY)=.+' ${INSTALL_DIR:-/opt/csgateway}/backend/.env | wc -l` output is >= 1

### on_failure
- pattern: "output is >= 1"
  recovery: "No model provider API key set. Export at least one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY"
  escalate: true

---

## step: Build Docker Images

### preconditions
- run: `docker compose version` exits 0
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/Dockerfile exists
- file: ${INSTALL_DIR:-/opt/csgateway}/frontend/Dockerfile exists

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
docker compose -f infra/docker-compose.dev.yml build --parallel
```

### verify
- run: `docker images | grep -c csgateway` output is >= 2

### on_failure
- pattern: "network.*timeout\|Could not resolve"
  recovery: "Network error during build. Check internet connectivity."
  then: retry
  max_retries: 2
- pattern: "no space left on device"
  recovery: |
    ```bash
    docker system prune -f
    ```
  then: retry
- pattern: ".*"
  recovery: "Docker build failed. Check build output above for errors."
  escalate: true

---

## step: Start Infrastructure Services

Start PostgreSQL (with pgvector) and Redis before the application.

### preconditions
- run: `docker compose version` exits 0
- file: ${INSTALL_DIR:-/opt/csgateway}/backend/.env exists

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

# Start database and cache
docker compose -f infra/docker-compose.dev.yml up -d postgres redis

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if docker exec csgateway-postgres pg_isready -U csgateway 2>/dev/null; then
        echo "PostgreSQL is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then echo "PostgreSQL timeout."; exit 1; fi
    sleep 1
done

# Wait for Redis
echo "Waiting for Redis..."
for i in $(seq 1 15); do
    if docker exec csgateway-redis redis-cli ping 2>/dev/null | grep -q PONG; then
        echo "Redis is ready."
        break
    fi
    if [ "$i" -eq 15 ]; then echo "Redis timeout."; exit 1; fi
    sleep 1
done
```

### verify
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0
- run: `docker exec csgateway-redis redis-cli ping` output contains "PONG"
- run: `docker ps --filter name=csgateway-postgres --filter status=running -q | wc -l` output is "1"
- run: `docker ps --filter name=csgateway-redis --filter status=running -q | wc -l` output is "1"

### on_failure
- pattern: "pg_isready.*timeout\|PostgreSQL timeout"
  recovery: |
    ```bash
    docker compose -f infra/docker-compose.dev.yml logs postgres --tail=20
    docker compose -f infra/docker-compose.dev.yml restart postgres
    sleep 15
    ```
  then: retry
  max_retries: 2
- pattern: "Redis timeout\|PONG.*not found"
  recovery: |
    ```bash
    docker compose -f infra/docker-compose.dev.yml restart redis
    sleep 5
    ```
  then: retry
- pattern: "port.*already.*use\|address already in use"
  recovery: "Port 5432 or 6379 is already in use. Stop the conflicting service or change ports in docker-compose.dev.yml."
  escalate: true
- pattern: ".*"
  recovery: "Check logs: `docker compose -f infra/docker-compose.dev.yml logs --tail=30`"
  escalate: true

---

## step: Run Database Migrations

### preconditions
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0
- step: "Start Infrastructure Services" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
docker compose -f infra/docker-compose.dev.yml run --rm backend bash -c "cd /app && alembic upgrade head"
```

### verify
- run: `docker exec csgateway-postgres psql -U csgateway -d csgateway -tAc "SELECT count(*) FROM alembic_version"` output is "1"
- run: `docker exec csgateway-postgres psql -U csgateway -d csgateway -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'" | tr -d ' '` output is >= 10

### on_failure
- pattern: "already at head\|No upgrade needed"
  action: continue
- pattern: "database.*does not exist"
  recovery: |
    ```bash
    docker exec csgateway-postgres createdb -U csgateway csgateway
    ```
  then: retry
- pattern: "Can't locate revision"
  recovery: |
    ```bash
    docker compose -f infra/docker-compose.dev.yml run --rm backend bash -c "cd /app && alembic stamp head"
    ```
  then: retry
  max_retries: 1
- pattern: ".*"
  recovery: "Migration failed. Check output above and: `docker compose -f infra/docker-compose.dev.yml run --rm backend bash -c 'alembic history'`"
  escalate: true

---

## step: Start All Services

### preconditions
- step: "Run Database Migrations" completed
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0
- run: `docker exec csgateway-redis redis-cli ping` output contains "PONG"

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
docker compose -f infra/docker-compose.dev.yml up -d

echo "Waiting for all services..."
sleep 20

echo ""
echo "=== Service Status ==="
docker compose -f infra/docker-compose.dev.yml ps
```

### verify
- run: `docker ps --filter name=csgateway-backend --filter status=running -q | wc -l` output is "1"
- run: `docker ps --filter name=csgateway-frontend --filter status=running -q | wc -l` output is "1"
- run: `curl -sf --max-time 15 http://localhost:8000/api/v1/health` exits 0
- run: `curl -s --max-time 15 http://localhost:8000/api/v1/health | grep -o '"status":"healthy"'` output contains "healthy"

### on_failure
- pattern: "Connection refused.*8000"
  recovery: |
    ```bash
    docker compose -f infra/docker-compose.dev.yml logs backend --tail=30
    docker compose -f infra/docker-compose.dev.yml restart backend
    sleep 15
    ```
  then: retry
  max_retries: 2
- pattern: "port.*already in use"
  recovery: "Port 8000, 3000, or 80 is in use. Stop the conflicting service or adjust ports in docker-compose.dev.yml."
  escalate: true
- pattern: ".*"
  recovery: |
    Check all service logs:
    ```bash
    docker compose -f infra/docker-compose.dev.yml logs --tail=30
    ```
  escalate: true

---

## step: Create Initial Admin Account

### preconditions
- run: `curl -sf http://localhost:8000/api/v1/health` exits 0

### action

```bash
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-changeme}"

echo "Creating admin account: ${ADMIN_EMAIL}"

curl -sf -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${ADMIN_EMAIL}\",
    \"password\": \"${ADMIN_PASSWORD}\",
    \"name\": \"Admin\"
  }" | python3 -m json.tool 2>/dev/null || echo "(account may already exist)"
```

### verify
- run: `curl -sf -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"email\":\"${ADMIN_EMAIL:-admin@localhost}\",\"password\":\"${ADMIN_PASSWORD:-changeme}\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'][:20])"` output is not empty

### on_failure
- pattern: "already exists\|duplicate"
  action: continue
- pattern: "Connection refused"
  recovery: "Backend is not responding. Check: `docker compose -f infra/docker-compose.dev.yml logs backend --tail=20`"
  escalate: true

---

## step: Verify Model Provider Connectivity

### preconditions
- run: `curl -sf http://localhost:8000/api/v1/health` exits 0

### action

```bash
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-changeme}"

TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")

echo "=== Available Models ==="
curl -sf http://localhost:8000/api/v1/models \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Provider Health ==="
curl -sf http://localhost:8000/api/v1/health/detailed \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### verify
- run: `curl -sf http://localhost:8000/api/v1/health/detailed | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['status'])"` output is "healthy"

### on_failure
- pattern: "No models\|models.*empty\|\\[\\]"
  recovery: "No models available. Verify API keys in backend/.env and restart: `docker compose -f infra/docker-compose.dev.yml restart backend`"
  escalate: true
- pattern: "invalid.*key\|authentication.*failed"
  recovery: "API key is invalid. Check the key in backend/.env, correct it, and restart the backend."
  escalate: true

---

## step: Final Verification

### preconditions
- step: "Start All Services" completed
- step: "Create Initial Admin Account" completed

### action

```bash
DOMAIN="${DOMAIN:-localhost}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"

echo "============================================"
echo "  CognitionShift Enterprise AI Gateway"
echo "  Installation Complete"
echo "============================================"
echo ""

echo "Service Health:"
curl -s http://localhost:8000/api/v1/health/detailed | python3 -m json.tool 2>/dev/null

echo ""
echo "Version:"
curl -s http://localhost:8000/api/v1/system/version | python3 -m json.tool 2>/dev/null

echo ""
echo "Access Points:"
echo "  Frontend:  http://${DOMAIN}:3000"
echo "  API:       http://${DOMAIN}:8000/api/v1/"
echo "  Health:    http://${DOMAIN}:8000/api/v1/health"
echo "  Nginx:     http://${DOMAIN}:80"
echo ""
echo "Admin Login:"
echo "  Email:     ${ADMIN_EMAIL}"
echo "  Password:  (as configured)"
echo ""
echo "Next Steps:"
echo "  1. Open http://${DOMAIN}:3000 and log in"
echo "  2. Follow configure.md for model setup, policies, and users"
echo "  3. Follow operate.md for monitoring and maintenance"
echo "============================================"
```

### verify
- run: `curl -sf http://localhost:8000/api/v1/health` exits 0
- run: `curl -sf http://localhost:8000/api/v1/health/detailed | python3 -c "import sys,json; d=json.load(sys.stdin)['data']['checks']; print(d['database'])"` output is "True"
- run: `curl -sf http://localhost:8000/api/v1/health/detailed | python3 -c "import sys,json; d=json.load(sys.stdin)['data']['checks']; print(d['redis'])"` output is "True"
- run: `curl -sf http://localhost:3000 --max-time 10` exits 0
- run: `docker compose -f ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.dev.yml ps --format '{{.State}}' | grep -v running | wc -l` output is "0"

### on_failure
- pattern: "database.*False"
  recovery: "Database health check failing. Run: `docker compose -f infra/docker-compose.dev.yml logs postgres --tail=20`"
  escalate: true
- pattern: "redis.*False"
  recovery: "Redis health check failing. Run: `docker compose -f infra/docker-compose.dev.yml logs redis --tail=20`"
  escalate: true
- pattern: ".*"
  recovery: "Verification failed. Run: `docker compose -f infra/docker-compose.dev.yml logs --tail=50`"
  escalate: true
