---
aeos: "0.1"
product: "CognitionShift Enterprise AI Gateway"
version: "0.1.0"
phase: backup
estimated_duration: "10m"
risk_level: low
required_tools:
  - name: docker
    check: "docker --version"
  - name: docker compose
    check: "docker compose version"
environment:
  optional:
    - name: INSTALL_DIR
      description: "Installation directory"
      default: "/opt/csgateway"
    - name: BACKUP_DIR
      description: "Directory for backup files"
      default: "/opt/csgateway/backups"
---

# Backup & Restore — CognitionShift Enterprise AI Gateway

Database backup, configuration backup, and disaster recovery procedures.

> This document follows the [Agent-Executable Operations Specification (AEOS)](https://github.com/CognitionShift/AEOS).

---

## step: Create Full Backup

Creates a database dump and configuration backup.

### preconditions
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0

### action

```bash
INSTALL_DIR="${INSTALL_DIR:-/opt/csgateway}"
BACKUP_DIR="${BACKUP_DIR:-${INSTALL_DIR}/backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "=== Database Backup ==="
docker exec csgateway-postgres pg_dump -U csgateway -Fc csgateway > "${BACKUP_DIR}/db-${TIMESTAMP}.sql"
echo "Database: ${BACKUP_DIR}/db-${TIMESTAMP}.sql ($(du -h ${BACKUP_DIR}/db-${TIMESTAMP}.sql | cut -f1))"

echo ""
echo "=== Configuration Backup ==="
cp "${INSTALL_DIR}/backend/.env" "${BACKUP_DIR}/env-${TIMESTAMP}.bak"
echo "Config: ${BACKUP_DIR}/env-${TIMESTAMP}.bak"

echo ""
echo "=== Git State ==="
cd "$INSTALL_DIR"
git rev-parse HEAD > "${BACKUP_DIR}/git-${TIMESTAMP}.ref"
echo "Git ref: $(cat ${BACKUP_DIR}/git-${TIMESTAMP}.ref)"

echo ""
echo "=== Backup Manifest ==="
cat > "${BACKUP_DIR}/manifest-${TIMESTAMP}.txt" << EOF
Backup: ${TIMESTAMP}
Database: db-${TIMESTAMP}.sql
Config: env-${TIMESTAMP}.bak
Git: $(cat ${BACKUP_DIR}/git-${TIMESTAMP}.ref)
Host: $(hostname)
Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

cat "${BACKUP_DIR}/manifest-${TIMESTAMP}.txt"
```

### verify
- run: `ls -la ${BACKUP_DIR:-/opt/csgateway/backups}/db-*.sql 2>/dev/null | tail -1 | awk '{print $5}'` output is >= 1000
- run: `ls ${BACKUP_DIR:-/opt/csgateway/backups}/env-*.bak 2>/dev/null | tail -1` output is not empty
- run: `ls ${BACKUP_DIR:-/opt/csgateway/backups}/manifest-*.txt 2>/dev/null | tail -1` output is not empty

### on_failure
- pattern: "Permission denied"
  recovery: |
    ```bash
    sudo mkdir -p ${BACKUP_DIR:-/opt/csgateway/backups}
    sudo chown $USER:$USER ${BACKUP_DIR:-/opt/csgateway/backups}
    ```
  then: retry
- pattern: "No space left"
  recovery: "Insufficient disk space for backup. Free space or use a different backup directory."
  escalate: true
- pattern: ".*"
  recovery: "Backup failed. Check Docker and database status."
  escalate: true

---

## step: Clean Old Backups

Remove backups older than 30 days to prevent disk exhaustion.

### preconditions
- file: ${BACKUP_DIR:-/opt/csgateway/backups} exists

### action

```bash
BACKUP_DIR="${BACKUP_DIR:-/opt/csgateway/backups}"
RETAIN_DAYS=30

echo "=== Cleaning backups older than ${RETAIN_DAYS} days ==="
BEFORE_COUNT=$(ls ${BACKUP_DIR}/db-*.sql 2>/dev/null | wc -l)

find "$BACKUP_DIR" -name "db-*.sql" -mtime +${RETAIN_DAYS} -delete -print
find "$BACKUP_DIR" -name "env-*.bak" -mtime +${RETAIN_DAYS} -delete -print
find "$BACKUP_DIR" -name "git-*.ref" -mtime +${RETAIN_DAYS} -delete -print
find "$BACKUP_DIR" -name "manifest-*.txt" -mtime +${RETAIN_DAYS} -delete -print

AFTER_COUNT=$(ls ${BACKUP_DIR}/db-*.sql 2>/dev/null | wc -l)
echo "Backups: ${BEFORE_COUNT} → ${AFTER_COUNT} (removed $((BEFORE_COUNT - AFTER_COUNT)))"
```

### verify
- run: `find ${BACKUP_DIR:-/opt/csgateway/backups} -name "db-*.sql" -mtime +30 | wc -l` output is "0"

---

## step: List Available Backups

### preconditions
- file: ${BACKUP_DIR:-/opt/csgateway/backups} exists

### action

```bash
BACKUP_DIR="${BACKUP_DIR:-/opt/csgateway/backups}"

echo "=== Available Backups ==="
for manifest in $(ls -t ${BACKUP_DIR}/manifest-*.txt 2>/dev/null); do
    echo "---"
    cat "$manifest"
    DBFILE=$(grep "^Database:" "$manifest" | awk '{print $2}')
    if [ -f "${BACKUP_DIR}/${DBFILE}" ]; then
        echo "Size: $(du -h ${BACKUP_DIR}/${DBFILE} | cut -f1)"
    fi
done

if [ ! -f "${BACKUP_DIR}/manifest-"*.txt 2>/dev/null ]; then
    echo "No backups found in ${BACKUP_DIR}"
    echo "Run 'Create Full Backup' step first."
fi
```

### verify
- run: `ls ${BACKUP_DIR:-/opt/csgateway/backups}/manifest-*.txt 2>/dev/null | wc -l` output is >= 1

### on_failure
- pattern: "output is >= 1"
  recovery: "No backups exist. Run the 'Create Full Backup' step."
  escalate: true

---

## step: Restore from Backup

Restores the database and configuration from a backup. **This will overwrite the current database.**

### preconditions
- run: `docker exec csgateway-postgres pg_isready -U csgateway` exits 0
- env: RESTORE_TIMESTAMP is set

### action

```bash
INSTALL_DIR="${INSTALL_DIR:-/opt/csgateway}"
BACKUP_DIR="${BACKUP_DIR:-${INSTALL_DIR}/backups}"
TS="${RESTORE_TIMESTAMP}"

echo "=== Restoring from backup: ${TS} ==="

# Verify backup files exist
if [ ! -f "${BACKUP_DIR}/db-${TS}.sql" ]; then
    echo "ERROR: Database backup not found: ${BACKUP_DIR}/db-${TS}.sql"
    echo "Available backups:"
    ls ${BACKUP_DIR}/db-*.sql 2>/dev/null
    exit 1
fi

echo "Backup manifest:"
cat "${BACKUP_DIR}/manifest-${TS}.txt" 2>/dev/null || echo "(no manifest)"

echo ""
echo "WARNING: This will overwrite the current database."
echo "Creating safety backup first..."

# Safety backup of current state
SAFETY_TS=$(date +%Y%m%d-%H%M%S)
docker exec csgateway-postgres pg_dump -U csgateway -Fc csgateway > "${BACKUP_DIR}/db-safety-${SAFETY_TS}.sql"
echo "Safety backup: db-safety-${SAFETY_TS}.sql"

echo ""
echo "Restoring database..."

# Drop and recreate
docker exec csgateway-postgres dropdb -U csgateway csgateway --if-exists
docker exec csgateway-postgres createdb -U csgateway csgateway

# Restore
docker exec -i csgateway-postgres pg_restore -U csgateway -d csgateway --no-owner < "${BACKUP_DIR}/db-${TS}.sql"

echo "Database restored."

# Restore config if available
if [ -f "${BACKUP_DIR}/env-${TS}.bak" ]; then
    cp "${INSTALL_DIR}/backend/.env" "${INSTALL_DIR}/backend/.env.pre-restore"
    cp "${BACKUP_DIR}/env-${TS}.bak" "${INSTALL_DIR}/backend/.env"
    chmod 600 "${INSTALL_DIR}/backend/.env"
    echo "Configuration restored."
fi

# Restore git ref if available
if [ -f "${BACKUP_DIR}/git-${TS}.ref" ]; then
    RESTORE_REF=$(cat "${BACKUP_DIR}/git-${TS}.ref")
    echo "Backup was from git ref: ${RESTORE_REF}"
    echo "Current ref: $(cd ${INSTALL_DIR} && git rev-parse HEAD)"
    echo "NOTE: Code is NOT automatically reverted. Run 'git checkout ${RESTORE_REF}' if needed."
fi

echo ""
echo "Restarting backend to pick up restored data..."
cd "$INSTALL_DIR"
docker compose -f infra/docker-compose.prod.yml restart backend
sleep 15
```

### verify
- run: `docker exec csgateway-postgres psql -U csgateway -d csgateway -tAc "SELECT count(*) FROM alembic_version"` output is "1"
- run: `curl -sf http://localhost:8000/api/v1/health/detailed | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['status'])"` output is "healthy"

### on_failure
- pattern: "database.*does not exist"
  recovery: |
    ```bash
    docker exec csgateway-postgres createdb -U csgateway csgateway
    ```
  then: retry
- pattern: "pg_restore.*error"
  recovery: |
    Restore failed. Recover from safety backup:
    ```bash
    SAFETY=$(ls -t ${BACKUP_DIR:-/opt/csgateway/backups}/db-safety-*.sql | head -1)
    docker exec csgateway-postgres dropdb -U csgateway csgateway --if-exists
    docker exec csgateway-postgres createdb -U csgateway csgateway
    docker exec -i csgateway-postgres pg_restore -U csgateway -d csgateway --no-owner < "$SAFETY"
    ```
  escalate: true
- pattern: ".*"
  recovery: "Restore failed. The safety backup preserves the pre-restore state."
  escalate: true

---

## monitor: Backup Freshness

### schedule
interval: 24h

### check
- run: `find ${BACKUP_DIR:-/opt/csgateway/backups} -name "db-*.sql" -mtime -1 | wc -l` output is >= 1

### on_degraded
- pattern: "output is >= 1"
  recovery: |
    No backup in the last 24 hours. Creating one now:
    ```bash
    cd ${INSTALL_DIR:-/opt/csgateway}
    BACKUP_DIR="${BACKUP_DIR:-/opt/csgateway/backups}"
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    mkdir -p "$BACKUP_DIR"
    docker exec csgateway-postgres pg_dump -U csgateway -Fc csgateway > "${BACKUP_DIR}/db-${TIMESTAMP}.sql"
    cp backend/.env "${BACKUP_DIR}/env-${TIMESTAMP}.bak"
    git rev-parse HEAD > "${BACKUP_DIR}/git-${TIMESTAMP}.ref"
    ```
  then: recheck
  escalate_after: 2 failures
