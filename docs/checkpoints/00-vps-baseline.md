# Checkpoint 00: VPS Baseline Verification

**Timestamp:** 2026-09-13T01:50:00+05:30  
**Host Environment:** Azure Standard_B1ms (Ubuntu 24.04.4 LTS)  
**Host Public IP:** `20.197.26.215`  
**SSH User:** `azureuser` (Port: 22)  
**Production Git Commit SHA:** `369229660e6e24419a551bbd046126a6d1bc3aa2`  
**Branch:** `main`  
**Working Tree Status:** Clean (no untracked, uncommitted, or modified files)

---

## 1. Service & Process Architecture

- **Systemd Unit:** `agency.service`
- **Unit Status:** Active (`active (running)`), PID 778
- **Command:** `/opt/agency/venv/bin/python -m app.service.runner`
- **Internal Host Binding:** `127.0.0.1:8000` (internal only, protected from public internet)
- **Reverse Proxy:** Caddy v2 (`:80`, `:443` HTTPS with automatic TLS certificate)
- **Worker Concurrency:** Single Uvicorn worker process running FastAPI lifespan + `agency_worker`

---

## 2. Security & Firewall Posture

- **UFW Status:** Active
- **Allowed Inbound Ports:**
  - `22/tcp` (SSH)
  - `80/tcp` (HTTP redirect)
  - `443/tcp` (HTTPS Caddy reverse proxy)
- **Blocked/Internal Ports:**
  - `8000/tcp` (FastAPI / Uvicorn internal service binding only)

---

## 3. Database & Backup Status

- **Database Path:** `/opt/agency/data/agency.db`
- **Storage Engine:** SQLite 3 in Write-Ahead Logging (`WAL`) mode (`journal_mode=wal`, `synchronous=NORMAL`)
- **Backup Directory:** `/opt/agency/backups`
- **Verified Archive:** `/opt/agency/backups/agency_backup_20260910_221602.db.gz` (1,029,917 bytes)
- **Backup Automated Cron:** `0 2 * * * /opt/agency/deploy/backup_sqlite.sh`

---

## 4. Operational Safety Invariants & Outbound Limits

- **`MAX_OUTREACH_PER_DAY`:** `1` (strictly enforced server-side)
- **`GMAIL_DAILY_CAPACITY`:** `1` (strictly enforced server-side)
- **Commercial Contract Floor:** `$500.00` minimum price floor preserved
- **Outbound Lock:** `ActiveOutreachLock` prevents concurrent sends
- **Zyte Scraping Status:** Shadow/Evaluation mode only (read-only, no automated mutation)

---

## 5. Current Production Outreach State

- **Business ID:** 30 (Orange Auto, Dubai)
- **Outreach Message ID:** 12
- **Outreach Message Status:** `PENDING_APPROVAL`
- **Recipient Email:** `info@orangeauto.ae`
- **Stored `approved_at`:** `2026-09-10 19:17:25.298532` (Subject of State Investigation #01)
- **Stored `sent_at`:** `NULL` (No email sent)
- **Safety Gate:** Message #12 is NOT approved; zero automated sends permitted.
