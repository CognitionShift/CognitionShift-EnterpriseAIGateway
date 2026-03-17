---
aeos: "0.1"
product: "CognitionShift Enterprise AI Gateway"
version: "0.1.0"
phase: update
estimated_duration: "15m"
risk_level: medium
rollback_strategy: "Restore database from pre-update backup, revert git to previous commit, rebuild containers"
required_tools:
  - name: docker
    check: "docker --version"
  - name: docker compose
    check: "docker compose version"
  - name: git
    check: "git --version"
  - name: curl
    check: "curl --version"
environment:
  optional:
    - name: INSTALL_DIR
      description: "Installation directory"
      default: "/opt/csgateway"
    - name: ADMIN_EMAIL
      default: "admin@localhost"
    - name: ADMIN_PASSWORD
      default: "changeme"
---

# Update — CognitionShift Enterprise AI Gateway

Apply software updates with backup, migration, and rollback at every step.

> This document follows the [Agent-Executable Operations Specification (AEOS)](https://github.com/CognitionShift/AEOS). Every step includes a rollback procedure. If any step fails, execute rollback steps in reverse order.

---

## step: Pre-Update Health Check

### preconditions
- run: `docker ps --filter name=csgateway --filter status=running -q | wc -l` output is >= 4

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

echo "=== Pre-Update Health ==="
curl -s https://${DOMAIN}/api/v1/health/detailed | python3 -m json.tool

echo ""
echo "=== Current Version ==="
curl -s https://${DOMAIN}/api/v1/system/version | python3 -m json.tool
echo "Git: $(git log --oneline -1)"
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/health/detailed | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['status'])"` output is "healthy"

### on_failure
- pattern: "healthy.*not found\|degraded"
  recovery: "System is unhealthy before update. Fix existing issues first — see operate.md troubleshooting."
  escalate: true

---

## step: Create Database Backup

### preconditions
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0
- step: "Pre-Update Health Check" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

BACKUP_FILE="backup-pre-update-$(date +%Y%m%d-%H%M%S).sql"
docker exec csgateway-postgres pg_dump -U csgateway -Fc csgateway > "${BACKUP_FILE}"
echo "Backup: ${BACKUP_FILE} ($(du -h ${BACKUP_FILE} | cut -f1))"
```

### verify
- run: `ls -la ${INSTALL_DIR:-/opt/csgateway}/backup-pre-update-*.sql 2>/dev/null | tail -1 | awk '{print $5}'` output is >= 1000

### on_failure
- pattern: "Permission denied"
  recovery: |
    ```bash
    sudo chown $USER:$USER ${INSTALL_DIR:-/opt/csgateway}
    ```
  then: retry
- pattern: ".*"
  recovery: "Database backup failed. Do NOT proceed with update."
  escalate: true

---

## step: Pull Latest Code

### preconditions
- step: "Create Database Backup" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

# Record current commit for rollback
git rev-parse HEAD > .previous-commit
echo "Current: $(cat .previous-commit)"

# Stash any local changes
git stash 2>/dev/null || true

# Pull latest
git pull origin main
echo "Updated: $(git rev-parse HEAD)"
echo "Changes: $(git log $(cat .previous-commit)..HEAD --oneline 2>/dev/null | wc -l) commits"
```

### verify
- file: ${INSTALL_DIR:-/opt/csgateway}/.previous-commit exists
- run: `cd ${INSTALL_DIR:-/opt/csgateway} && git log --oneline -1` output is not empty

### on_failure
- pattern: "merge conflict"
  recovery: |
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    git merge --abort
    git reset --hard origin/main
    ```
  then: retry
  max_retries: 1
- pattern: ".*"
  recovery: "Git pull failed. Check network and repository access."
  escalate: true

### rollback
```bash
cd ${INSTALL_DIR:-/opt/csgateway}
git checkout $(cat .previous-commit)
```

---

## step: Rebuild Docker Images

### preconditions
- step: "Pull Latest Code" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
docker compose -f infra/docker-compose.prod.yml build --parallel
```

### verify
- run: `docker images | grep -c csgateway` output is >= 2

### on_failure
- pattern: "no space left"
  recovery: |
    ```bash
    docker system prune -f
    ```
  then: retry
- pattern: ".*"
  recovery: "Docker build failed. Check build output above."
  escalate: true

---

## step: Apply Database Migrations

### preconditions
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0
- step: "Create Database Backup" completed
- step: "Pull Latest Code" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"
docker compose -f infra/docker-compose.prod.yml run --rm backend bash -c "cd /app && alembic upgrade head"
```

### verify
- run: `docker compose -f ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.prod.yml run --rm backend bash -c "cd /app && alembic check" 2>&1` output contains "up to date"

### on_failure
- pattern: "already at head\|up to date"
  action: continue
- pattern: "Can't locate revision"
  recovery: "Migration history mismatch. This requires manual investigation."
  escalate: true
- pattern: ".*"
  recovery: |
    Restore from backup:
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    BACKUP=$(ls -t backup-pre-update-*.sql | head -1)
    docker exec -i csgateway-postgres pg_restore -U csgateway -d csgateway --clean < "$BACKUP"
    ```
  escalate: true

### rollback
```bash
cd ${INSTALL_DIR:-/opt/csgateway}
docker compose -f infra/docker-compose.prod.yml run --rm backend bash -c "cd /app && alembic downgrade -1"
```

---

## step: Restart Services

### preconditions
- step: "Apply Database Migrations" completed
- step: "Rebuild Docker Images" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

docker compose -f infra/docker-compose.prod.yml up -d --force-recreate backend frontend nginx
echo "Waiting for services..."
sleep 20

docker ps --filter name=csgateway --format 'table {{.Names}}\t{{.Status}}'
```

### verify
- run: `docker ps --filter name=csgateway --filter status=running -q | wc -l` output is >= 4
- run: `curl -sf --max-time 15 https://${DOMAIN}/api/v1/health` exits 0
- run: `curl -sf https://${DOMAIN}/api/v1/health/detailed | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['status'])"` output is "healthy"

### on_failure
- pattern: "Connection refused\|unhealthy"
  recovery: |
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    docker compose -f infra/docker-compose.prod.yml logs backend --tail=30
    docker compose -f infra/docker-compose.prod.yml restart backend
    sleep 15
    ```
  then: retry
  max_retries: 2
- pattern: ".*"
  recovery: "Services failed after update. Consider rolling back."
  escalate: true

### rollback
```bash
cd ${INSTALL_DIR:-/opt/csgateway}
git checkout $(cat .previous-commit)
docker compose -f infra/docker-compose.prod.yml build --parallel
docker compose -f infra/docker-compose.prod.yml up -d --force-recreate
sleep 20
```

---

## step: Post-Update Verification

### preconditions
- step: "Restart Services" completed

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

echo "=== Post-Update Health ==="
curl -s https://${DOMAIN}/api/v1/health/detailed | python3 -m json.tool

echo ""
echo "=== Updated Version ==="
curl -s https://${DOMAIN}/api/v1/system/version | python3 -m json.tool
echo "Git: $(git log --oneline -1)"

echo ""
echo "=== Quick Smoke Test ==="
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-changeme}"

TOKEN=$(curl -sf -X POST https://${DOMAIN}/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])" 2>/dev/null)

if [ -n "$TOKEN" ]; then
    echo "  Auth:   ✓"
    MODELS=$(curl -sf https://${DOMAIN}/api/v1/models \
      -H "Authorization: Bearer $TOKEN" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',d)))" 2>/dev/null)
    echo "  Models: ✓ ($MODELS available)"
else
    echo "  Auth:   ✗ (could not log in)"
fi

echo ""
echo "Update complete. Cleaning up..."
rm -f .previous-commit
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/health/detailed | python3 -c "import sys,json; d=json.load(sys.stdin)['data']['checks']; print(d['database'] and d['redis'])"` output is "True"
- run: `curl -sf https://${DOMAIN} --max-time 10` exits 0

### on_failure
- pattern: ".*"
  recovery: "Post-update verification failed. Review the failure and decide whether to roll back."
  escalate: true
