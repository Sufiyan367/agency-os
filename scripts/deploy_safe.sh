#!/usr/bin/env bash
# ==============================================================================
# SAFE ATOMIC DEPLOYMENT RUNNER FOR AGENCY OS
# ==============================================================================
# Usage: ./scripts/deploy_safe.sh [branch]
#
# Workflow:
#   1. Preflight check (clean working tree, records pre-deploy commit)
#   2. Pre-deployment database backup (online SQLite backup with integrity check)
#   3. Fast-forward pull of latest code
#   4. Asset integrity check (templates, CSS, JS)
#   5. Restart systemd daemon (agency.service)
#   6. Post-deployment health polling loop (up to 20s)
#   7. If health fails -> AUTOMATIC ROLLBACK to pre-deploy commit
# ==============================================================================

set -euo pipefail

APP_DIR="/opt/agency"
TARGET_BRANCH="${1:-main}"
LOG_FILE="/var/log/agency_deployment.log"
HEALTH_URL="http://127.0.0.1:8000/health"
MAX_HEALTH_ATTEMPTS=10
SLEEP_SECONDS=2

# Helper logging
log() {
    local msg="[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] [Deploy] $1"
    echo "$msg"
    if [ -w "$(dirname "$LOG_FILE")" ]; then
        echo "$msg" >> "$LOG_FILE"
    fi
}

cd "$APP_DIR"

log "Starting safe deployment on branch: $TARGET_BRANCH"

# 1. Preflight Checks
PRE_DEPLOY_COMMIT=$(git rev-parse HEAD)
log "Pre-deployment commit SHA: $PRE_DEPLOY_COMMIT"

if [ -n "$(git status --porcelain)" ]; then
    log "WARNING: Working tree has uncommitted local modifications. Stashing..."
    git stash push -m "pre_deploy_stash_$(date +%s)"
fi

# 2. Automated Pre-Deployment Database Backup
log "Creating pre-deployment database backup..."
if [ -f "/opt/agency/venv/bin/python3" ]; then
    /opt/agency/venv/bin/python3 scripts/run_backup.py
else
    python3 scripts/run_backup.py
fi
log "Pre-deployment database backup verified."

# 3. Pull latest changes
log "Fetching and fast-forwarding to origin/$TARGET_BRANCH..."
git fetch origin "$TARGET_BRANCH"
git checkout "$TARGET_BRANCH"
git pull --ff-only origin "$TARGET_BRANCH"
POST_PULL_COMMIT=$(git rev-parse HEAD)
log "Updated to commit: $POST_PULL_COMMIT"

# 4. Verify Critical Assets Exist
log "Verifying frontend and backend asset integrity..."
test -f app/frontend/templates/index.html || { log "ERROR: index.html missing!"; exit 1; }
test -f app/frontend/static/style.css || { log "ERROR: style.css missing!"; exit 1; }
test -f app/api/app.py || { log "ERROR: app.py missing!"; exit 1; }

# 5. Restart Systemd Daemon
log "Restarting agency.service..."
sudo systemctl restart agency

# 6. Health Verification Polling Loop
log "Polling $HEALTH_URL for readiness..."
HEALTHY=0
for i in $(seq 1 $MAX_HEALTH_ATTEMPTS); do
    sleep "$SLEEP_SECONDS"
    HTTP_CODE=$(curl -s -o /tmp/deploy_health.json -w "%{http_code}" "$HEALTH_URL" || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        STATUS=$(grep -o '"status":"[^"]*"' /tmp/deploy_health.json | cut -d'"' -f4 || echo "unknown")
        OVERALL=$(grep -o '"overall_state":"[^"]*"' /tmp/deploy_health.json | cut -d'"' -f4 || echo "unknown")
        if [ "$STATUS" = "ok" ] || [ "$OVERALL" = "HEALTHY" ]; then
            log "Health check PASSED on attempt $i (HTTP 200, status=$STATUS, overall=$OVERALL)"
            HEALTHY=1
            break
        fi
    fi
    log "Attempt $i: HTTP $HTTP_CODE (waiting $SLEEP_SECONDS seconds)..."
done

if [ "$HEALTHY" -eq 1 ]; then
    log "DEPLOYMENT SUCCESSFUL! Running at commit: $POST_PULL_COMMIT"
    exit 0
fi

# 7. AUTOMATIC ROLLBACK TRIGGERED
log "ERROR: Health check failed after deployment! Initiating AUTOMATIC ROLLBACK to $PRE_DEPLOY_COMMIT..."
git checkout "$PRE_DEPLOY_COMMIT"
sudo systemctl restart agency

# Verify rollback health
sleep 3
ROLLBACK_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo "000")
if [ "$ROLLBACK_CODE" = "200" ]; then
    log "ROLLBACK RECOVERY SUCCESSFUL. System restored to $PRE_DEPLOY_COMMIT and serving traffic."
else
    log "CRITICAL: Rollback attempted but system still unhealthy (HTTP $ROLLBACK_CODE). Manual investigation required."
fi

exit 1
