#!/usr/bin/env bash
# ==============================================================================
# Autonomous B2B Lead-Gen & Sales Agency — Cloud VPS 1-Command Automated Deployer
# Sets up a 24/7 unattended production server on Ubuntu/Debian Linux VPS.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}=================================================================${NC}"
echo -e "${CYAN}  Autonomous B2B Lead-Gen & Sales Agency — 24/7 Cloud Deployer   ${NC}"
echo -e "${CYAN}=================================================================${NC}"

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}[ERROR] This script must be run as root (or via sudo).${NC}"
    exit 1
fi

DEPLOY_DIR="/opt/agency"
mkdir -p "$DEPLOY_DIR"

echo -e "\n${YELLOW}Step 1: Installing System Dependencies & Docker...${NC}"
apt-get update -qq
apt-get install -y -qq \
    curl \
    git \
    ufw \
    ca-certificates \
    gnupg \
    lsb-release

if ! command -v docker &> /dev/null; then
    echo -e "Installing Docker Engine..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

if ! docker compose version &> /dev/null; then
    echo -e "Installing Docker Compose Plugin..."
    apt-get install -y -qq docker-compose-plugin
fi

echo -e "\n${YELLOW}Step 2: Configuring UFW Firewall (SSH, HTTP, HTTPS)...${NC}"
ufw allow 22/tcp || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw --force enable || true

echo -e "\n${YELLOW}Step 3: Configuring Production Environment Variables...${NC}"
ENV_FILE="$DEPLOY_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "Generating secure cryptographic secrets..."
    GEN_PASS=$(openssl rand -hex 12)
    GEN_API_KEY=$(openssl rand -hex 24)
    GEN_SESSION_KEY=$(openssl rand -hex 24)

    cat <<EOF > "$ENV_FILE"
# ==============================================================================
# Autonomous Agency — Production Cloud Environment
# ==============================================================================
APP_NAME=Autonomous B2B Lead-Gen & Sales Agency
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Cloud Domain & HTTPS (Set your real domain name for automatic Let's Encrypt SSL)
DOMAIN=localhost
TLS_EMAIL=admin@example.com

# Production Authentication
AUTH_ENABLED=true
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=${GEN_PASS}
API_SECRET_KEY=${GEN_API_KEY}
SESSION_SECRET=${GEN_SESSION_KEY}

# Persistent Database Storage
DATABASE_URL=sqlite+aiosqlite:////app/data/agency.db
SYNC_DATABASE_URL=sqlite:////app/data/agency.db
BACKUP_DIR=/app/backups
BACKUP_RETENTION_DAYS=30

# Safeguards & Compliance
DRY_RUN=true
EMAIL_DRY_RUN=true
EMAIL_PROVIDER=dry_run
PAYMENT_PROVIDER=dry_run
PAYMENTS_ENABLED=false
MAX_OUTREACH_PER_DAY=50
MAX_FOLLOWUPS=3

# Background Worker Cadence
WORKER_ENABLED=true
WORKER_CYCLE_INTERVAL_MINUTES=30
EOF
    chmod 600 "$ENV_FILE"
    echo -e "${GREEN}✓ Production .env created with secure secrets.${NC}"
else
    echo -e "Existing .env found at $ENV_FILE. Preserving configuration."
fi

echo -e "\n${YELLOW}Step 4: Launching 24/7 Production Docker Stack...${NC}"
cd "$DEPLOY_DIR"

if [ -f "deploy/docker-compose.prod.yml" ]; then
    docker compose -f deploy/docker-compose.prod.yml up -d --build
else
    echo -e "${YELLOW}Please copy the repository files into $DEPLOY_DIR and run:${NC}"
    echo -e "  cd $DEPLOY_DIR && docker compose -f deploy/docker-compose.prod.yml up -d --build"
fi

echo -e "\n${YELLOW}Step 5: Setting Up Automated Nightly Database Backups...${NC}"
BACKUP_CRON="/etc/cron.daily/agency-backup"
cat << 'CRON_EOF' > "$BACKUP_CRON"
#!/usr/bin/env bash
docker exec agency-app python -m app.cli backup > /var/log/agency_backup.log 2>&1
CRON_EOF
chmod +x "$BACKUP_CRON"

echo -e "\n${GREEN}=================================================================${NC}"
echo -e "${GREEN}  ✓ 24/7 CLOUD VPS DEPLOYMENT COMPLETED SUCCESSFULLY!            ${NC}"
echo -e "${GREEN}=================================================================${NC}"
echo -e "• Background Worker & API: Running 24/7 (Restarts automatically on crash/reboot)"
echo -e "• Laptop Dependency:       NONE (Server runs continuously unattended)"
echo -e "• Web Dashboard URL:       https://your-server-ip or https://your-domain"
echo -e "• Dashboard Username:      admin"
echo -e "• Dashboard Password:      (Stored in $ENV_FILE)"
echo -e "• Database Persistence:    Volume 'agency_production_data'"
echo -e "• Automated Backups:       Daily at /etc/cron.daily/agency-backup"
echo -e "================================================================="
