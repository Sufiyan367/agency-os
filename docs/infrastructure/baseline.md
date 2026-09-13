# Agency OS — Production Infrastructure Baseline

**Audited Timestamp**: 2026-09-13 13:10 UTC  
**Environment**: Production Cloud VPS (`agency-vps` / Azure VM)  
**Host IP**: `20.197.26.215` (Private subnet `172.16.0.4`)  
**Domain**: `https://automatedagencyos.tech`

---

## 1. Hardware & Operating System

| Metric | Measured Value | Operational Assessment |
| :--- | :--- | :--- |
| **OS Distribution** | Ubuntu 24.04.4 LTS (Noble Numbat) | Modern LTS, current security patch set |
| **Linux Kernel** | `6.17.0-1022-azure` x86_64 | Optimized Azure cloud kernel |
| **Virtual CPU** | 1 vCPU (`nproc: 1`) | Sufficient for async FastAPI single-daemon architecture |
| **RAM Total** | 1,903 MB (~2.0 GB) | Resource-constrained; cgroup memory caps mandatory |
| **RAM Used** | ~840 MB (44%) | Agency daemon + Caddy running smoothly |
| **RAM Available** | 1,063 MB (56%) | Healthy buffer for async worker cycles |
| **Swap Space** | 2,047 MB total (0 MB used) | 100% available headroom for memory pressure spikes |
| **Disk Storage** | 29 GB total (`/dev/root`) | 5.3 GB used (19%), 23 GB available (81% free) |
| **Inode Usage** | 3.8M inodes total (10% used) | Over 3.4M free inodes |

---

## 2. Network & Firewall Topology

```
Internet (Users & Webhooks)
        │
    Ports 80/443 (HTTP/HTTPS)
        ▼
   [ UFW Firewall ] ─── Port 22/tcp (SSH via Key Only)
        │
   [ Caddy Reverse Proxy ]
        │ TLS Termination, Compression (zstd/gzip), Security Headers
        ▼
   127.0.0.1:8000 (FastAPI Agency Daemon — LOCALHOST ONLY)
```

### UFW Rules
- `Status`: active
- `Default`: deny (incoming), allow (outgoing), disabled (routed)
- `Rules`:
  - `22/tcp`: ALLOW IN Anywhere (SSH, public key authentication only)
  - `80/tcp`: ALLOW IN Anywhere (HTTP -> HTTPS redirect)
  - `443/tcp`: ALLOW IN Anywhere (HTTPS)
  - **Port 8000**: NOT ALLOWED public access. Bound strictly to `127.0.0.1:8000`.

### Listening Sockets (`ss -tulpn`)
- `tcp 127.0.0.1:8000`: `python` daemon (`agency.service`)
- `tcp 0.0.0.0:80, :443`: `caddy` reverse proxy
- `tcp 127.0.0.1:2019`: `caddy` admin API (localhost only)
- `tcp 0.0.0.0:22`: `sshd`

---

## 3. Reverse Proxy & Security Headers (`/etc/caddy/Caddyfile`)
- **Domain**: `automatedagencyos.tech`
- **Compression**: `zstd gzip`
- **Security Headers**:
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy`: scoped self-origins with CDN script/style allowlists
  - `Server`: Header stripped
- **Logging**: JSON structured access logs at `/var/log/caddy/agency_access.log` with automatic roll (50MB, 5 retained).

---

## 4. Application Daemon (`agency.service`)
- **Path**: `/etc/systemd/system/agency.service`
- **User/Group**: `agency:agency`
- **Working Directory**: `/opt/agency`
- **Virtualenv**: `/opt/agency/venv` (Python 3.12.3)
- **Entrypoint**: `/opt/agency/venv/bin/python -m app.service.runner`
- **Restart Policy**: `always`, `RestartSec=5s`
- **Shutdown Grace**: `TimeoutStopSec=30s`, `KillMode=mixed`
- **Security**: `NoNewPrivileges=true`, `ProtectSystem=full`, `ProtectHome=true`, `PrivateTmp=true`
- **Resource Hardening**: `LimitNOFILE=65535`, `MemoryHigh=1200M`, `MemoryMax=1500M`, `TasksMax=100`

---

## 5. Database Architecture
- **Engine**: SQLite 3.45+ in WAL (Write-Ahead Logging) mode
- **Location**: `/opt/agency/data/agency.db` (6.3 MB)
- **WAL / SHM**: `/opt/agency/data/agency.db-wal` (4.1 MB), `agency.db-shm` (32 KB)
- **PRAGMAs**: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=15000`
- **Latency**: 1.01 ms
- **Alembic Version**: `001_initial_schema` (78 tables registered and verified)

---

## 6. Safety Baseline & Canary State
- **OutreachMessage #12 (Orange Auto, Business #30)**: Status `APPROVED`, `sent_at=NULL` (0 live dispatches).
- **Daily Outbound Cap**: 1 max (Level 1 Canary).
- **ActiveOutreachLock**: `IDLE`.
- **Payments Gateway**: `razorpay` (Disabled, simulation safe).
- **Auth**: Enabled (`AUTH_ENABLED=True`).
