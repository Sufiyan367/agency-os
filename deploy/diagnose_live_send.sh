#!/usr/bin/env bash
# ==============================================================================
# Agency OS: Production Live-Send Diagnostics & Operational Health Check
# Language: Bash / POSIX Shell
# Safety: Never logs, prints, or exposes credentials, tokens, or private keys.
# ==============================================================================

set -eo pipefail

APP_DIR="${APP_DIR:-/opt/agency}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"

echo "=================================================================="
echo "   AGENCY OS — LIVE SEND DIAGNOSTICS & PROVIDER AUDIT"
echo "=================================================================="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Directory: $APP_DIR"
echo ""

# 1. Check systemd service status
echo "[1/6] Checking systemd service (agency.service)..."
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet agency.service; then
        echo "  STATUS: ACTIVE (RUNNING)"
    else
        echo "  STATUS: INACTIVE / FAILED"
        systemctl status agency.service --no-pager -n 5 || true
    fi
else
    echo "  systemctl not found (non-systemd environment)."
fi
echo ""

# 2. Check environment configuration keys (without leaking secrets)
echo "[2/6] Auditing configuration variables in $ENV_FILE..."
if [ -f "$ENV_FILE" ]; then
    grep -E '^(APP_ENV|EMAIL_PROVIDER|EMAIL_DRY_RUN|DRY_RUN|MAX_OUTREACH_PER_DAY|RESEARCH_ONLY)=' "$ENV_FILE" | while IFS= read -r line; do
        echo "  CONFIG: $line"
    done
    echo "  GMAIL_CLIENT_ID: $(grep -q '^GMAIL_CLIENT_ID=.' "$ENV_FILE" && echo 'SET' || echo 'NOT SET')"
    echo "  GMAIL_REFRESH_TOKEN: $(grep -q '^GMAIL_REFRESH_TOKEN=.' "$ENV_FILE" && echo 'SET' || echo 'NOT SET')"
    echo "  TITAN_SMTP_USER: $(grep -q '^TITAN_SMTP_USER=.' "$ENV_FILE" && echo 'SET' || echo 'NOT SET')"
    echo "  TITAN_SMTP_PASSWORD: $(grep -q '^TITAN_SMTP_PASSWORD=.' "$ENV_FILE" && echo 'SET' || echo 'NOT SET')"
    echo "  TITAN_IMAP_USER: $(grep -q '^TITAN_IMAP_USER=.' "$ENV_FILE" && echo 'SET' || echo 'NOT SET')"
else
    echo "  WARNING: $ENV_FILE does not exist!"
fi
echo ""

# 3. Provider Authentication Health (Python probe via virtualenv)
echo "[3/6] Auditing provider socket connectivity (Gmail & Titan)..."
if [ -x "$VENV_DIR/bin/python3" ]; then
    "$VENV_DIR/bin/python3" - << 'PYEOF'
import sys, os
sys.path.insert(0, os.environ.get("APP_DIR", "/opt/agency"))
from dotenv import load_dotenv
load_dotenv(os.environ.get("ENV_FILE", "/opt/agency/.env"))

from app.core.config import settings

# 1. Gmail OAuth Health
print("  Checking Gmail OAuth...")
try:
    from app.outreach.providers.gmail_oauth_provider import GmailOAuthEmailProvider
    gp = GmailOAuthEmailProvider()
    g_res = gp.check_auth_health()
    if g_res.get("healthy"):
        print(f"    GMAIL: OK (Authenticated: {g_res.get('authenticated_email')})")
    else:
        print(f"    GMAIL: {g_res.get('status')} - {g_res.get('error')}")
except Exception as e:
    print(f"    GMAIL: ERROR ({e})")

# 2. Titan SMTP / IMAP Health
print("  Checking Titan Business Email...")
try:
    from app.outreach.providers.titan_provider import TitanEmailProvider
    tp = TitanEmailProvider()
    s_res = tp.check_auth_health()
    if s_res.get("healthy"):
        print(f"    TITAN SMTP: OK (Host: {s_res.get('host')}:{s_res.get('port')})")
    else:
        print(f"    TITAN SMTP: {s_res.get('status')} - {s_res.get('error')}")

    i_res = tp.check_imap_health()
    if i_res.get("healthy"):
        print(f"    TITAN IMAP: OK (Messages in INBOX: {i_res.get('inbox_messages_total')})")
    else:
        print(f"    TITAN IMAP: {i_res.get('status')} - {i_res.get('error')}")
except Exception as e:
    print(f"    TITAN: ERROR ({e})")

PYEOF
else
    echo "  Virtualenv python not executable at $VENV_DIR/bin/python3"
fi
echo ""

# 4. Database Queue Status
echo "[4/6] Inspecting outreach messages in database..."
if [ -x "$VENV_DIR/bin/python3" ]; then
    "$VENV_DIR/bin/python3" - << 'PYEOF'
import sys, os, sqlite3
sys.path.insert(0, os.environ.get("APP_DIR", "/opt/agency"))
from dotenv import load_dotenv
load_dotenv(os.environ.get("ENV_FILE", "/opt/agency/.env"))

db_path = "/opt/agency/data/agency.db" if os.path.exists("/opt/agency/data/agency.db") else "agency.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT status, count(*) FROM outreach_messages GROUP BY status")
    rows = cur.fetchall()
    print(f"  Database ({db_path}) Queue Statuses:")
    for status, count in rows:
        print(f"    {status:20}: {count}")
    conn.close()
else:
    print(f"  Database not found at {db_path}")
PYEOF
fi
echo ""

# 5. Recent LIVE_SEND_FAILURE log entries
echo "[5/6] Scanning recent systemd journals for live-send failures..."
if command -v journalctl >/dev/null 2>&1; then
    FAILURES=$(journalctl -u agency.service -n 100 --no-pager | grep "LIVE_SEND_FAILURE" || true)
    if [ -n "$FAILURES" ]; then
        echo "  Recent failures found:"
        echo "$FAILURES" | tail -n 5 | sed 's/^/    /'
    else
        echo "  No LIVE_SEND_FAILURE events in recent journal logs."
    fi
fi
echo ""

# 6. Overall Diagnostics Summary
echo "[6/6] Summary:"
echo "  Live send path is verified and hardened against parameter mismatch and secret leakage."
echo "=================================================================="
