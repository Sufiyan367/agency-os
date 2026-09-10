#!/usr/bin/env bash
# ==============================================================================
# Agency OS — Automated SQLite Online Backup Script
# Performs non-blocking, online SQLite snapshot with gzip compression
# and integrity verification. Designed for daily cron (/etc/cron.daily/agency-backup).
# ==============================================================================

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agency}"
LOG_FILE="/var/log/agency_backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE" 2>/dev/null || echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting Agency OS SQLite backup..."

if [ ! -d "$APP_DIR" ]; then
    log "ERROR: Agency directory $APP_DIR does not exist."
    exit 1
fi

cd "$APP_DIR"

# 1. Use the virtualenv Python if available, else system python3
if [ -x "$APP_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$APP_DIR/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
else
    log "ERROR: Python interpreter not found."
    exit 1
fi

# 2. Execute the verified Agency OS DatabaseBackupManager CLI
if "$PYTHON_BIN" -m app.cli backup >> "$LOG_FILE" 2>&1; then
    log "✓ Agency OS SQLite backup created and verified successfully."
    exit 0
else
    log "WARNING: CLI backup returned non-zero. Attempting raw sqlite3 online fallback..."
fi

# 3. Fallback: Native sqlite3 CLI online backup
DB_FILE="$APP_DIR/data/agency.db"
BACKUP_DIR="$APP_DIR/backups"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
TEMP_BACKUP="$BACKUP_DIR/raw_backup_${TIMESTAMP}.db"
FINAL_BACKUP="$BACKUP_DIR/agency_backup_${TIMESTAMP}.db.gz"

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_FILE" ] && command -v sqlite3 &>/dev/null; then
    log "Running sqlite3 .backup to $TEMP_BACKUP..."
    sqlite3 "$DB_FILE" ".backup '$TEMP_BACKUP'"
    
    # Verify backup integrity
    INTEGRITY=$(sqlite3 "$TEMP_BACKUP" "PRAGMA integrity_check;")
    if [ "$INTEGRITY" = "ok" ]; then
        gzip -c "$TEMP_BACKUP" > "$FINAL_BACKUP"
        rm -f "$TEMP_BACKUP"
        log "✓ Raw fallback backup verified and compressed: $FINAL_BACKUP"
        
        # Prune backups older than 30 days
        find "$BACKUP_DIR" -name "agency_backup_*.db.gz" -mtime +30 -delete
        exit 0
    else
        log "ERROR: Fallback backup failed integrity check: $INTEGRITY"
        rm -f "$TEMP_BACKUP"
        exit 1
    fi
else
    log "ERROR: Database file or sqlite3 tool not found."
    exit 1
fi
