# Agency OS — CEO Browser Accessibility & Deployment Guide

## 1. Executive Summary: Zero-Command Browser Operation

Agency OS is built to enable seamless browser-based operation for the CEO and non-technical stakeholders without requiring any terminal or command-line execution:

1. **One-Click Windows Launcher**:
   - `Launch_Agency_OS.bat`: Double-click to automatically check if the server is running on port 8000. If offline, it starts the backend server in the background, waits for `/health` to verify 200 OK status, and launches the CEO Dashboard directly in the default web browser (`http://localhost:8000/dashboard`).
   - `Launch_Agency_OS.vbs`: A silent wrapper that executes the batch launcher completely hidden with zero command-line windows or terminal prompts.
2. **Web Portal Link**:
   - Visitors and operators visiting the public business website (`http://localhost:8000/` or public domain) have a dedicated **Portal** button in the header navigation that links directly to `/dashboard`.
3. **Live Health Telemetry**:
   - The CEO Control Center includes an active backend reachability badge (`#ceo-backend-health-pill`) in the top navigation bar and a `Backend API` status indicator in the System Status & Safeguards card. If the server is unreachable or experiences connectivity degradation, the UI displays real-time status.

---

## 2. Production Deployment Architecture

Agency OS is an autonomous operations system consisting of:
- **FastAPI ASGI Server**: Provides REST APIs, SSE/Websocket event streaming, and serves the vanilla JS CEO Control Center.
- **Persistent Relational Database**: SQLite (or PostgreSQL) storing businesses, prospects, leads, proposals, audit logs, and compliance records.
- **Persistent Background Workers**: Active IMAP inbox listener polling for incoming emails, signal intercepts, and autonomous background cycle dispatchers.

### Recommended Production Targets

| Deployment Target | Best For | Persistent DB | Background Worker Support |
| :--- | :--- | :--- | :--- |
| **Linux VPS (Docker Compose + Caddy)** | Production (24/7) | Yes (Mounted volume) | Full persistent asyncio worker |
| **Systemd Service (deploy/agency.service)** | Dedicated VPS | Yes (Native file) | Full persistent systemd service |
| **Local Windows/Mac** | CEO Laptop / Workstation | Yes (`agency.db`) | Background daemon via launcher |

Production automated script is provided at `deploy/setup_vps.sh` and orchestrated via `deploy/docker-compose.prod.yml`.

---

## 3. Vercel Deployment Investigation & Post-Mortem

### Why `agency-os-n6yx` Succeeded on Vercel
- The `agency-os-n6yx` project was configured on Vercel with **Root Directory set to `public/`** (or configured as a static HTML/CSS/JS site).
- In this configuration, Vercel acts as a static Content Delivery Network (CDN), serving `public/index.html` and `public/static/website.css` without requiring a Python build step or executing serverless functions.

### Why `agency-os`, `agency-os-wkxh`, `agency-os-5ke4`, and `agencygrowth` Failed
1. **Repository Root Target (`.`)**:
   - These projects were configured pointing to the root of the repository without a static directory override.
2. **Serverless Python Runtime Limitations**:
   - Vercel attempted to build the root repository as Python Serverless Functions.
   - The repository includes compiled C-extensions and dependencies (e.g. `psycopg`, `asyncpg`, `duckduckgo-search`, `alembic`, `pydantic-settings`) that exceed Vercel's serverless package size limits.
3. **Stateless Ephemeral Containers**:
   - Vercel serverless functions spin down to 0 after every request. SQLite (`agency.db`) cannot persist across serverless invocations; any changes are wiped upon function termination.
4. **No Background Worker Lifecycle**:
   - Agency OS requires continuous background IMAP email monitoring and asynchronous lead processing. Serverless functions cannot run persistent event loops or long-lived background threads.

### Conclusion & Rule of Thumb
- **Do not compromise application code** to fit serverless platforms.
- The public landing website can be deployed to Vercel statically (Root Directory = `public`).
- The full Agency OS backend, database, and background workers run on persistent infrastructure (Docker, VPS, or local workstation).
