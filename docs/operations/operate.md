---
aeos: "0.1"
product: "CognitionShift Enterprise AI Gateway"
version: "0.1.0"
phase: operate
estimated_duration: "ongoing"
risk_level: low
required_tools:
  - name: docker
    check: "docker --version"
  - name: docker compose
    check: "docker compose version"
  - name: curl
    check: "curl --version"
environment:
  optional:
    - name: INSTALL_DIR
      description: "Installation directory"
      default: "/opt/csgateway"
---

# Operate — CognitionShift Enterprise AI Gateway

Ongoing monitoring, health checks, log management, and troubleshooting.

> This document follows the [Agent-Executable Operations Specification (AEOS)](https://github.com/CognitionShift/AEOS).

**Note:** All commands assume `$DOMAIN` is set. On the server, run `source /opt/csgateway/infra/.env` first, or set `DOMAIN=your-domain.com`.

---

## monitor: Platform Health

### schedule
interval: 5m

### check
- run: `curl -sf --max-time 10 https://${DOMAIN}/api/v1/health` exits 0
- run: `curl -sf --max-time 10 https://${DOMAIN}/api/v1/health/detailed | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['status'])"` output is "healthy"
- run: `docker ps --filter name=csgateway --filter status=running -q | wc -l` output is >= 4

### on_degraded
- pattern: "database.*False\|database.*unhealthy"
  recovery: |
    ```bash
    docker restart csgateway-postgres
    sleep 15
    docker exec csgateway-postgres pg_isready -U csgateway
    ```
  then: recheck
  escalate_after: 3 failures

- pattern: "redis.*False\|redis.*unhealthy"
  recovery: |
    ```bash
    docker restart csgateway-redis
    sleep 5
    ```
  then: recheck
  escalate_after: 2 failures

- pattern: "Connection refused\|curl.*failed"
  recovery: |
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    docker compose -f infra/docker-compose.prod.yml up -d
    sleep 20
    ```
  then: recheck
  escalate_after: 2 failures

---

## monitor: Model Provider Health

### schedule
interval: 15m

### check
- run: `curl -sf --max-time 15 https://${DOMAIN}/api/v1/health/detailed | python3 -c "import sys,json; p=json.load(sys.stdin)['data']['checks'].get('providers',{}); failed=[k for k,v in p.items() if not v]; print('OK' if not failed else ' '.join(failed))"` output is "OK"

### on_degraded
- pattern: "openai"
  recovery: "OpenAI provider unreachable. Check https://status.openai.com/ — fallback models will handle traffic automatically."
  escalate_after: 6 failures

- pattern: "anthropic"
  recovery: "Anthropic provider unreachable. Check https://status.anthropic.com/ — fallback models will handle traffic automatically."
  escalate_after: 6 failures

- pattern: "google"
  recovery: "Google AI provider unreachable. Fallback models will handle traffic automatically."
  escalate_after: 6 failures

---

## monitor: Disk Space

### schedule
interval: 1h

### check
- run: `df --output=pcent / | tail -1 | tr -d ' %'` output is <= 85
- run: `docker system df --format '{{.Size}}' | head -1` output is not empty

### on_degraded
- pattern: "output is <= 85"
  recovery: |
    ```bash
    docker system prune -f
    find /var/lib/docker/containers/ -name "*-json.log" -size +100M -exec truncate -s 0 {} \;
    echo "Cleaned Docker resources and truncated large log files."
    ```
  then: recheck
  escalate_after: 2 failures

---

## monitor: Container Restarts

### schedule
interval: 30m

### check
- run: `docker ps --filter name=csgateway --format '{{.Names}} {{.Status}}' | grep -c 'Restarting'` output is "0"

### on_degraded
- pattern: ".*"
  recovery: |
    A container is restart-looping. Check which one:
    ```bash
    docker ps --filter name=csgateway --format 'table {{.Names}}\t{{.Status}}'
    ```
  escalate: true

---

## step: View Service Status

### preconditions
- run: `docker ps -q | wc -l` output is >= 1

### action

```bash
echo "=== Service Status ==="
docker ps --filter name=csgateway --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo ""
echo "=== Resource Usage ==="
docker stats --no-stream --filter name=csgateway --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}'

echo ""
echo "=== Health ==="
curl -s https://${DOMAIN}/api/v1/health/detailed | python3 -m json.tool 2>/dev/null

echo ""
echo "=== Version ==="
curl -s https://${DOMAIN}/api/v1/system/version | python3 -m json.tool 2>/dev/null
```

### verify
- run: `docker ps --filter name=csgateway --filter status=running -q | wc -l` output is >= 4

### on_failure
- pattern: ".*"
  recovery: "Some services are not running. Check: `docker compose -f ${INSTALL_DIR:-/opt/csgateway}/infra/docker-compose.prod.yml logs --tail=20`"
  escalate: true

---

## step: View Logs

### preconditions
- run: `docker ps --filter name=csgateway -q | wc -l` output is >= 1

### action

```bash
echo "=== Recent Backend Logs (last 50 lines) ==="
docker logs csgateway-backend --tail=50 --timestamps 2>&1

echo ""
echo "=== Recent PostgreSQL Logs ==="
docker logs csgateway-postgres --tail=20 --timestamps 2>&1

echo ""
echo "=== Recent Redis Logs ==="
docker logs csgateway-redis --tail=10 --timestamps 2>&1
```

### verify
- run: `docker logs csgateway-backend --tail=1 2>&1 | wc -l` output is >= 1

---

## step: Restart Application

Use when the backend is misbehaving but infrastructure (database, Redis) is healthy.

### preconditions
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0
- run: `docker exec csgateway-redis redis-cli ping` output contains "PONG"

### action

```bash
cd "${INSTALL_DIR:-/opt/csgateway}"

echo "Restarting application services..."
docker compose -f infra/docker-compose.prod.yml restart backend frontend nginx
sleep 15

echo "=== Status After Restart ==="
docker ps --filter name=csgateway --format 'table {{.Names}}\t{{.Status}}'
```

### verify
- run: `curl -sf --max-time 15 https://${DOMAIN}/api/v1/health` exits 0
- run: `docker ps --filter name=csgateway --filter status=running -q | wc -l` output is >= 4

### on_failure
- pattern: "Connection refused\|unhealthy"
  recovery: |
    Full restart:
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    docker compose -f infra/docker-compose.prod.yml down
    docker compose -f infra/docker-compose.prod.yml up -d
    sleep 25
    ```
  then: retry
  max_retries: 1

---

## step: Check Usage Statistics

### preconditions
- run: `curl -sf https://${DOMAIN}/api/v1/health` exits 0

### action

```bash
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@localhost}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-changeme}"

TOKEN=$(curl -sf -X POST https://${DOMAIN}/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")

echo "=== Usage Summary (Daily) ==="
curl -sf "https://${DOMAIN}/api/v1/usage/summary?period=daily" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Usage by Model ==="
curl -sf "https://${DOMAIN}/api/v1/usage/breakdown?group_by=model&days=7" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Recent Safety Events ==="
curl -sf "https://${DOMAIN}/api/v1/admin/safety-events?days=7&limit=5" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### verify
- run: `curl -sf https://${DOMAIN}/api/v1/usage/summary -H "Authorization: Bearer $TOKEN"` exits 0

---

## troubleshoot: Application Returns 502

### symptoms
- Browser shows "502 Bad Gateway"
- curl to port 80 returns 502
- Direct curl to port 8000 may or may not respond

### diagnostic_steps

1. **Check if backend container is running**
   - run: `docker ps --filter name=csgateway-backend --format '{{.Status}}'`
   - if empty or "Exited": `docker start csgateway-backend`, wait 15s, retry
   - if "Restarting": check logs — `docker logs csgateway-backend --tail=30`
   - if "Up": continue to step 2

2. **Check if backend is responding**
   - run: `curl -sf https://${DOMAIN}/api/v1/health`
   - if exits non-zero: backend is up but not accepting requests — check logs
   - if exits 0: backend is fine, problem is nginx routing — continue to step 3

3. **Check nginx configuration**
   - run: `docker exec csgateway-nginx nginx -t`
   - if "syntax is ok": `docker restart csgateway-nginx`
   - if syntax error: check nginx.conf in `infra/nginx/nginx.conf`

4. **Check networking between containers**
   - run: `docker exec csgateway-nginx curl -sf http://backend:8000/api/v1/health`
   - if "Could not resolve": Docker network issue — `docker compose down && docker compose up -d`

---

## troubleshoot: Slow Responses

### symptoms
- Time to first token > 5 seconds
- Users report long loading times
- Overall latency elevated

### diagnostic_steps

1. **Check model provider latency**
   - run: `curl -sf https://${DOMAIN}/api/v1/health/detailed | python3 -m json.tool`
   - if providers show degraded/slow: upstream issue, not the gateway

2. **Check database connections**
   - run: `docker exec csgateway-postgres psql -U csgateway -d csgateway -tAc "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"`
   - if count > 20: connection pool may be saturated — restart backend

3. **Check Redis latency**
   - run: `docker exec csgateway-redis redis-cli --latency-history -i 1 | head -5`
   - if latency > 10ms: Redis may be overloaded — check memory usage

4. **Check container resource usage**
   - run: `docker stats --no-stream --filter name=csgateway`
   - if any container > 90% CPU or memory: increase resource limits in docker-compose

---

## troubleshoot: Cannot Log In

### symptoms
- Login returns 401 or 500
- "Invalid credentials" despite correct password
- Login page doesn't load

### diagnostic_steps

1. **Check backend is running**
   - run: `curl -sf https://${DOMAIN}/api/v1/health`
   - if fails: backend is down — see "Application Returns 502" troubleshoot

2. **Test auth endpoint directly**
   - run: `curl -v -X POST https://${DOMAIN}/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@localhost","password":"changeme"}'`
   - if 500: check backend logs — database may be unreachable
   - if 401: credentials are wrong — reset password via database

3. **Reset admin password**
   - run: |
     ```bash
     # Generate new bcrypt hash and update
     docker exec csgateway-backend python3 -c "
     from passlib.hash import bcrypt
     print(bcrypt.hash('new-password-here'))
     " | xargs -I{} docker exec csgateway-postgres psql -U csgateway -d csgateway \
       -c "UPDATE users SET password_hash='{}' WHERE email='admin@localhost'"
     ```
