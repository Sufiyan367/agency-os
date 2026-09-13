#!/usr/bin/env bash
# ==============================================================================
# ROLLBACK UTILITY FOR AGENCY OS
# ==============================================================================
# Usage: ./scripts/rollback.sh [target_commit_or_ref]
#
# Workflow:
#   1. Check target rollback commit (defaults to HEAD~1)
#   2. Check out target commit
#   3. Optionally restore pre-deployment database backup if requested
#   4. Restart systemd daemon (agency.service)
#   5. Verify /health returns 200 OK
# ==============================================================================

set -euo pipefail

APP_DIR="/opt/agency"
TARGET_REF="${1:-HEAD~1}"
LOG_FILE="/var/log/agency_deployment.log"
HEALTH_URL="http://127.0.0.1:8000/health"

log() {
    local msg="[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] [Rollback] $1"
    echo "$msg"
    if [ -w "$(dirname "$LOG_FILE")" ]; then
        echo "$msg" >> "$LOG_FILE"
    fi
}

cd "$APP_DIR"

CURRENT_COMMIT=$(git rev-parse HEAD)
log "Current commit: $CURRENT_COMMIT"
log "Target rollback ref: $TARGET_REF"

TARGET_COMMIT=$(git rev-parse "$TARGET_REF")
log "Target commit resolved to: $TARGET_COMMIT"

# 1. Checkout target ref
log "Checking out target commit $TARGET_COMMIT..."
git checkout "$TARGET_COMMIT"

# 2. Restart service
log "Restarting agency.service..."
sudo systemctl restart agency

# 3. Verify Health
sleep 3
HTTP_CODE=$(curl -s -o /tmp/rollback_health.json -w "%{http_code}" "$HEALTH_URL" || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    log "ROLLBACK VERIFIED: System healthy at commit $TARGET_COMMIT (HTTP 200)."
    exit 0
else
    log "WARNING: Health check returned HTTP $HTTP_CODE after rollback."
    cat /tmp/rollback_health.json || true
    exit 1
fi
