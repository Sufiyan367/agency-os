# Agency OS — 24/7 VPS Production Deployment Runbook

> **Target Audience**: Primary Production Engineer & CEO  
> **Repository**: `S:\AGENCY\BY AG` (GitHub: `Sufiyan367/agency-os`)  
> **Production Safety Level**: Stage-1 Canary (Strictly 1 Real Email/Day Max)  
> **Commercial Floor**: $\ge \$500$ USD  
> **Database Architecture**: SQLite with WAL mode & AsyncIO (Preserved)

---

## 1. Executive Summary & Architecture

Agency OS is architected for unattended **24/7 continuous operation** on a budget Linux VPS (e.g. Hetzner, OVH, DigitalOcean, or Oracle Cloud Free Tier). Once deployed:
- **No Laptop Dependency**: Runs continuously in the cloud; laptop can be powered off.
- **CEO Browser/Mobile Control**: All operational tasks (prospect review, queue approval, campaign monitoring, reply tracking) are performed via browser/mobile at `https://your-domain.com/dashboard`.
- **Zero Terminal for Normal Ops**: The CEO never needs to use SSH or command-line tools for routine acquisition.
- **₹0 Before First Payment**: No paid database services (PostgreSQL), paid message brokers (Redis/RabbitMQ), or paid monitoring tools.
- **Production Source of Truth**: `ExistingDiscoveryAdapterProvider` (OpenStreetMap + public web) is the primary discovery provider. Zyte operates strictly in shadow/evaluation mode.

```
Internet (Port 80/443)
        ↓
Caddy Reverse Proxy (Automatic Let's Encrypt TLS / HTTPS)
        ↓ (Port 8000)
FastAPI ASGI Server (Single-worker Uvicorn managed by systemd)
  ├── Lifespan Supervisor
  │     ├── Persistent Agency Worker (Reply polling, attention engine, cadences)
  │     └── Revenue Agent Orchestrator (Optional autonomous loops)
  ├── REST API & Static CEO Dashboard (/dashboard, /login)
  └── SQLite with WAL Mode (/opt/agency/data/agency.db)
```

---

## 2. VPS Prerequisites

| Requirement | Specification | Notes |
| :--- | :--- | :--- |
| **Operating System** | Ubuntu 22.04 LTS or 24.04 LTS | Standard 64-bit x86_64 or ARM64 |
| **Compute** | 1 vCPU, 1 GB to 2 GB RAM | Minimum 1 GB RAM (add 2 GB swap if 1 GB RAM) |
| **Storage** | 20+ GB SSD / NVMe | SQLite DB + backups + rotating logs |
| **Network** | Static public IPv4, Ports 22, 80, 443 | Domain DNS A-record pointing to VPS IP |
| **Python** | Python 3.11 or 3.12 | Standard `python3-venv` and `python3-pip` |
| **Software Cost** | **₹0.00** | Uses open-source stack and existing free tiers |

---

## 3. Step-by-Step Server Setup

### Step 3.1: Host Hardening & Firewall
SSH into your VPS as `root`:

```bash
# Update package repositories
apt-get update && apt-get upgrade -y

# Install essential dependencies
apt-get install -y curl git ufw sqlite3 ca-certificates gnupg python3 python3-venv python3-pip

# Configure UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP Let's Encrypt'
ufw allow 443/tcp comment 'HTTPS Caddy'
ufw --force enable
```

### Step 3.2: Create Dedicated Non-Root Service User
```bash
useradd -m -s /bin/bash agency
usermod -aG sudo agency  # Optional for admin tasks

# Create application directories
mkdir -p /opt/agency /opt/agency/data /opt/agency/logs /opt/agency/backups
chown -R agency:agency /opt/agency
```

### Step 3.3: Clone Codebase & Setup Python Environment
Log in as the `agency` user:

```bash
su - agency
cd /opt/agency

# Clone the repository
git clone https://github.com/Sufiyan367/agency-os.git .
git checkout main

# Create virtual environment & install dependencies
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3.4: Configure Production Secrets & Environment
Create `/opt/agency/.env` and restrict file permissions:

```bash
cat << 'EOF' > /opt/agency/.env
# ==============================================================================
# Agency OS — Production Cloud Environment Configuration
# ==============================================================================
APP_NAME=Autonomous B2B Lead-Gen & Sales Agency
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Domain & Reverse Proxy
DOMAIN=agency.yourdomain.com
TLS_EMAIL=admin@yourdomain.com

# Authentication (Generate strong random passwords)
AUTH_ENABLED=true
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=REPLACE_WITH_SECURE_ADMIN_PASSWORD
VIEWER_USERNAME=viewer
VIEWER_PASSWORD=REPLACE_WITH_SECURE_VIEWER_PASSWORD
API_SECRET_KEY=REPLACE_WITH_OPENSSL_HEX_32
SESSION_SECRET=REPLACE_WITH_OPENSSL_HEX_32

# Database: SQLite with WAL mode & AsyncIO
DATABASE_URL=sqlite+aiosqlite:////opt/agency/data/agency.db
SYNC_DATABASE_URL=sqlite:////opt/agency/data/agency.db
BACKUP_DIR=/opt/agency/backups
BACKUP_RETENTION_DAYS=30

# Commercial Safety Policy
COMMERCIAL_FLOOR_USD=500
ONE_AT_A_TIME_PROSPECTING=true

# Stage-1 Canary Outbound Limits (Strictly 1 Real Email/Day)
DRY_RUN=false
EMAIL_DRY_RUN=false
EMAIL_PROVIDER=gmail_oauth
MAX_OUTREACH_PER_DAY=1
MAX_FOLLOWUPS=3
AUTONOMOUS_OUTREACH=false

# Gmail OAuth Credentials (Loaded securely via environment)
GMAIL_CLIENT_ID=your_client_id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your_client_secret
GMAIL_REFRESH_TOKEN=your_refresh_token
GMAIL_SENDER_EMAIL=your_email@gmail.com
GMAIL_DAILY_CAPACITY=1

# Discovery Engine (Primary: Existing Web Search; Zyte: Shadow Evaluation)
ZYTE_API_KEY=
ZYTE_MODE=evaluation
ZYTE_CREDIT_BUDGET=50

# Payments (Razorpay / Stripe)
PAYMENT_PROVIDER=razorpay
PAYMENTS_ENABLED=false
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
RAZORPAY_CURRENCY=USD

# Background Worker Cadence
WORKER_ENABLED=true
WORKER_INTERVAL_SECONDS=60
WORKER_CYCLE_INTERVAL_MINUTES=30
AUTONOMOUS_AUTO_DISCOVERY=false
EOF

# Lock down permissions: readable and writable ONLY by the agency user
chmod 600 /opt/agency/.env
```

### Step 3.5: Initialize Database Schema & Baseline Seeds
```bash
source /opt/agency/venv/bin/activate
python -m app.cli init
```

---

## 4. Process Supervision Setup (Systemd)

Systemd guarantees **automatic restart upon process failure** and **automatic boot on VPS startup**, while maintaining a single Uvicorn instance (`--workers 1`) to eliminate write lock contention on SQLite.

### Step 4.1: Install & Enable Service Unit
As `root`:

```bash
cp /opt/agency/deploy/agency.service /etc/systemd/system/agency.service
systemctl daemon-reload
systemctl enable agency.service
systemctl start agency.service
```

### Step 4.2: Verify Service Status & Logs
```bash
# Check service status
systemctl status agency.service

# Follow real-time application logs
journalctl -u agency.service -f
```

---

## 5. Reverse Proxy & HTTPS Setup (Caddy)

Caddy automatically provisions, installs, and renews Let's Encrypt / ZeroSSL TLS certificates with zero manual intervention.

### Step 5.1: Install Caddy
As `root`:

```bash
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy
```

### Step 5.2: Configure Caddyfile
Copy `deploy/Caddyfile` to `/etc/caddy/Caddyfile`:

```bash
cp /opt/agency/deploy/Caddyfile /etc/caddy/Caddyfile

# Replace {$DOMAIN} with your actual registered domain
sed -i 's/{\$DOMAIN:localhost}/agency.yourdomain.com/g' /etc/caddy/Caddyfile

# Restart Caddy to activate automatic HTTPS
systemctl reload caddy
```

Verify HTTPS is active:
```bash
curl -I https://agency.yourdomain.com/health
```

---

## 6. Automated Daily SQLite Backup Setup

SQLite backups are performed **online** without stopping the server or interrupting concurrent read/write operations using the native SQLite backup API.

### Step 6.1: Install Daily Backup Cron Job
As `root`:

```bash
chmod +x /opt/agency/deploy/backup_sqlite.sh
ln -sf /opt/agency/deploy/backup_sqlite.sh /etc/cron.daily/agency-backup
```

### Step 6.2: Test Backup Execution
```bash
/opt/agency/deploy/backup_sqlite.sh
ls -lh /opt/agency/backups/
```
You will see an integrity-verified, gzip-compressed snapshot like `agency_backup_YYYYMMDD_HHMMSS.db.gz`.

---

## 7. Health & Telemetry Verification

Agency OS provides deep diagnostic telemetry through `/api/health` without exposing any secrets or credentials.

Execute:
```bash
curl -s http://localhost:8000/api/health | jq
```

Expected Response:
```json
{
  "status": "ok",
  "overall_state": "HEALTHY",
  "service": "Autonomous B2B Lead-Gen & Sales Agency",
  "env": "production",
  "database": {
    "status": "connected",
    "dialect": "sqlite",
    "latency_ms": 1.25
  },
  "worker": {
    "is_running": true,
    "ticks_executed": 42,
    "last_tick_at": "2026-09-11T02:40:00Z"
  },
  "gmail": {
    "provider": "gmail_oauth",
    "configured": true,
    "dry_run": false,
    "sender_email": "suf***@gmail.com",
    "oauth_ready": true
  },
  "discovery": {
    "primary_provider": "existing_web_search",
    "registered_providers": ["existing_web_search", "scrapegraph_ai", "zyte_api"],
    "available_providers": ["existing_web_search"],
    "zyte_mode": "evaluation",
    "me_phase1_target_daily": 70
  },
  "outreach": {
    "rollout_stage": "Pilot Single-Outreach (Canary)",
    "daily_cap": 1,
    "sent_today": 0,
    "available_capacity": 1,
    "commercial_floor_usd": 500.0,
    "active_lock_status": "IDLE"
  },
  "payment": {
    "provider": "razorpay",
    "enabled": false,
    "currency": "USD"
  },
  "cloud_mode": true,
  "auth_enabled": true
}
```

---

## 8. Middle East Phase-1 Discovery Operations (70/Day Target)

The 7 Phase-1 Middle East corridors are:
1. **UAE** (`AE`) — 10 qualified prospects/day
2. **Saudi Arabia** (`SA`) — 10 qualified prospects/day
3. **Qatar** (`QA`) — 10 qualified prospects/day
4. **Kuwait** (`KW`) — 10 qualified prospects/day
5. **Oman** (`OM`) — 10 qualified prospects/day
6. **Bahrain** (`BH`) — 10 qualified prospects/day
7. **Jordan** (`JO`) — 10 qualified prospects/day
**Total**: **70 qualified prospects/day**.

### Running Discovery Manually via CLI
```bash
su - agency
cd /opt/agency
source venv/bin/activate

# Execute discovery across all 7 countries (halts prior to outreach)
python -m app.cli discover-me-phase1 --target-per-country 10
```

### Triggering Discovery via CEO Dashboard
In the web dashboard, navigate to **Global Acquisition & Outreach** $\rightarrow$ Click **Run Multi-Country Discovery**.  
The backend executes discovery asynchronously, enriches website audits, and populates the ranked queue.

> [!IMPORTANT]
> Discovery target is **NOT** an email-sending target. All discovered prospects remain stored in the database. Outbound emails are governed strictly by the Stage-1 Canary limit (1 real email/day) and require deliberate human review/approval.

---

## 9. Verifying Outbound Remains Locked to Stage-1 Canary

Run the capacity verification:
```bash
python -c "
import asyncio
from app.database.connection import AsyncSessionLocal
from app.campaigns.sender_registry import sender_registry

async def check():
    async with AsyncSessionLocal() as s:
        summary = await sender_registry.get_sender_capacity_summary(s)
        assert summary['rollout_daily_cap'] == 1, 'SAFETY VIOLATION: Daily cap != 1'
        print('✓ Confirmed: Rollout daily cap is strictly', summary['rollout_daily_cap'], 'email/day.')

asyncio.run(check())
"
```

---

## 10. Disaster Recovery & Rollback Runbook

### Scenario 1: Worker or API Crash
The systemd supervisor automatically detects process exit and restarts the service within 5 seconds (`RestartSec=5s`).
```bash
systemctl status agency.service
journalctl -u agency.service -n 100 --no-pager
```

### Scenario 2: VPS Reboot
The service unit has `WantedBy=multi-user.target`. Upon reboot, systemd automatically mounts the database and starts the FastAPI server and worker.

### Scenario 3: Restoring Database from Backup
```bash
# 1. Stop the application service
systemctl stop agency.service

# 2. Select backup file and restore
su - agency
cd /opt/agency
source venv/bin/activate
python -m app.cli restore /opt/agency/backups/agency_backup_YYYYMMDD_HHMMSS.db.gz

# 3. Verify SQLite integrity
sqlite3 /opt/agency/data/agency.db "PRAGMA integrity_check;"

# 4. Restart service
exit # back to root
systemctl start agency.service
```

### Scenario 4: Rollback Codebase to Previous Git Commit
```bash
su - agency
cd /opt/agency
git log -n 5 --oneline
git checkout <PREVIOUS_STABLE_COMMIT_HASH>

exit # back to root
systemctl restart agency.service
```

---

## 11. Production Safety Invariants Checklist

Before leaving the deployment unattended, verify every invariant:

- [x] **Zero Commits of Secrets**: `.env`, `client_secrets.json`, and credentials are gitignored.
- [x] **SQLite WAL Mode**: `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=10000;` verified active.
- [x] **Outbound Limit**: Stage-1 Canary strictly enforced at 1 real email/day.
- [x] **Commercial Floor**: Minimum value $\ge \$500$ USD strictly enforced.
- [x] **Orange Auto Canary**: ID #12 remains in `PENDING_APPROVAL` (not dispatched).
- [x] **No WhatsApp Automation**: WhatsApp remains strictly non-automated.
- [x] **No Telephony Spend**: Voice providers remain in `dry_run` mode.
- [x] **Zyte Crawling Mode**: Operates strictly in shadow/evaluation mode.
- [x] **Daily Automated Backup**: Daily cron installed and verified.
