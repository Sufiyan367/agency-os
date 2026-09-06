# Docker Security Verification Checklist

This checklist documents the security controls applied to containerized deployments of the Autonomous B2B Lead-Gen & Sales Agency platform.

## 1. Principle of Least Privilege
- [x] **Non-Root Execution**: Container process runs as unprivileged user `appuser` (`UID 10001`, `GID 10001`).
- [x] **No Root Access**: User does not possess sudo or wheel permissions.
- [x] **Dedicated Home & Workdir**: `/app` is owned by `appuser:appuser` with strict read/write bounds.

## 2. Kernel & Capability Restriction
- [x] **Privilege Escalation Blocked**: `security_opt: ["no-new-privileges:true"]` prevents setuid/setgid privilege escalation.
- [x] **Capability Drops**: `cap_drop: ["ALL"]` drops all default Linux kernel capabilities.
- [x] **Minimal Allowed Capabilities**: Only minimal required capabilities (`CHOWN`, `SETUID`, `SETGID`) retained for process start.

## 3. Network & Exposure Boundary
- [x] **Localhost Port Binding**: Port mapped to `127.0.0.1:8000:8000`, preventing direct public WAN exposure without an authenticated reverse proxy (e.g. Caddy/Nginx with TLS).
- [x] **Zero Database Port Exposure**: SQLite database mounted via volume; zero raw DB ports exposed to network.
- [x] **Minimal Attack Surface**: Only single HTTP/WebSocket port (8000) exposed.

## 4. Secret & State Management
- [x] **No Baked Secrets**: Zero credentials, tokens, or private keys baked into Docker image layers.
- [x] **Runtime Environment Injection**: Secrets injected via secure `.env` or orchestrator environment variables at runtime.
- [x] **Sensitive Path Exclusions**: `.dockerignore` and `.gitignore` exclude `data/`, `*.db`, `*.log`, `credentials*`, and `secrets*`.

## 5. Health & Observability
- [x] **Automated Healthcheck**: Docker `HEALTHCHECK` periodically audits `http://localhost:8000/health`.
- [x] **Graceful Shutdown**: Container traps SIGTERM and stops background workers gracefully within 30s.
