# Agency OS — Safe Deployment & Rollback Runbook

**Document Owner**: DevOps / SRE  
**Execution Standard**: Automated, Gated, Self-Healing

---

## 1. Deployment Principles
1. **Pre-flight Backup Mandatory**: Every production deployment automatically creates a compressed, verified SQLite database snapshot before pulling code.
2. **Fast-Forward Only**: Deployments strictly require fast-forward git merges (`git pull --ff-only`).
3. **Automated Health Gate**: The service is polled at `/health` for up to 20 seconds post-restart.
4. **Self-Healing Rollback**: If the service fails to return `HTTP 200` with `status: ok` / `overall_state: HEALTHY`, the deployment runner **automatically checks out the pre-deploy commit** and restores service.

---

## 2. Standard Production Deployment Command

From the VPS terminal:
```bash
sudo /opt/agency/scripts/deploy_safe.sh main
```

### What `deploy_safe.sh` Executes:
1. Records `PRE_DEPLOY_COMMIT` SHA.
2. Stashes any working tree changes.
3. Runs `scripts/run_backup.py` to create a verified snapshot in `/opt/agency/backups/`.
4. Fetches and fast-forwards to `origin/main`.
5. Verifies frontend and backend file existence (`index.html`, `style.css`, `app.py`).
6. Restarts `agency.service`.
7. Polls `http://127.0.0.1:8000/health` up to 10 attempts (every 2 seconds).
8. **On Success**: Logs `DEPLOYMENT SUCCESSFUL` to `/var/log/agency_deployment.log` and exits 0.
9. **On Failure**: Triggers automatic git checkout of `PRE_DEPLOY_COMMIT`, restarts `agency.service`, verifies recovery, and exits 1.

---

## 3. Manual Rollback Procedure (`scripts/rollback.sh`)

If a manual rollback is required:
```bash
# Roll back to immediate previous commit
sudo /opt/agency/scripts/rollback.sh HEAD~1

# Or roll back to a specific known-good commit
sudo /opt/agency/scripts/rollback.sh <COMMIT_SHA>
```

---

## 4. Post-Deployment Verification Checklist

After every deployment, verify:
- [ ] `curl -s http://127.0.0.1:8000/health | grep '"status":"ok"'`
- [ ] `curl -s http://127.0.0.1:8000/health | grep '"overall_state":"HEALTHY"'`
- [ ] Canary #12 invariant: `(12, 30, 'APPROVED', None)`
- [ ] Outbound cap remains 1 max
- [ ] Web dashboard reachable at `https://automatedagencyos.tech/dashboard`
- [ ] Public site reachable at `https://automatedagencyos.tech/`
