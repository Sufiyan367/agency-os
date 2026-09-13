# Agency OS — Database Backup & Disaster Recovery Runbook

**Document Owner**: DevOps / Reliability Engineering  
**Recovery Targets**:
- **Recovery Point Objective (RPO)**: **60 Minutes** (Maximum acceptable data loss window)
- **Recovery Time Objective (RTO)**: **15 Minutes** (Maximum acceptable recovery downtime)

---

## 1. Backup Architecture

### Automated Hourly Snapshots
- **Service**: `agency-backup.service`
- **Timer**: `agency-backup.timer` (Triggers every 60 minutes: `*:00:00 UTC`)
- **CLI Script**: `python3 /opt/agency/scripts/run_backup.py`
- **Storage Directory**: `/opt/agency/backups`
- **Naming Pattern**: `agency_backup_YYYYMMDD_HHMMSS.db.gz`
- **Compression**: Gzip Level 9 (typically 80%–85% storage savings)
- **Retention**: 30 days (older backups automatically pruned upon creation)
- **Integrity Validation**: Every backup executes `PRAGMA integrity_check;` before compression.

---

## 2. Controlled Verification & Testing

### Non-Destructive Restore Test (`scripts/test_restore.py`)
To prove that backups can be restored without touching production:
```bash
cd /opt/agency
python3 scripts/test_restore.py
```
**Test Workflow**:
1. Locates latest `agency_backup_*.db.gz`.
2. Restores into an isolated temporary database path (`/tmp/agency_restore_test_XXXX/restored_test.db`).
3. Executes `PRAGMA integrity_check`.
4. Validates table row counts across `businesses`, `outreach_messages`, `users`, `campaigns`, `proposals`.
5. Confirms Canary #12 (`APPROVED`, `sent_at=None`) invariant inside the restored target.
6. Cleans up temporary artifacts.

---

## 3. Production Disaster Recovery Procedure

### Scenario A: Rollback to Pre-Deployment Snapshot
If a bad deployment corrupted database state:
```bash
# 1. Stop the application daemon
sudo systemctl stop agency

# 2. Identify the target backup file
ls -lah /opt/agency/backups/

# 3. Restore using DatabaseBackupManager or CLI
cd /opt/agency
sudo -u agency /opt/agency/venv/bin/python3 -c "
from app.database.backup import backup_manager
backup_manager.restore_backup('agency_backup_YYYYMMDD_HHMMSS.db.gz')
"

# 4. Verify integrity
sudo -u agency sqlite3 /opt/agency/data/agency.db "PRAGMA integrity_check;"

# 5. Restart application daemon
sudo systemctl start agency
sudo systemctl status agency

# 6. Verify health
curl -s http://127.0.0.1:8000/health | jq .
```

### Scenario B: Complete Server Disaster Recovery
If the VPS is rebuilt from scratch:
1. Re-clone repository: `git clone https://github.com/Sufiyan367/agency-os /opt/agency`
2. Set up virtualenv: `python3 -m venv /opt/agency/venv && /opt/agency/venv/bin/pip install -r requirements.txt`
3. Restore database snapshot from cold backup storage into `/opt/agency/data/agency.db`.
4. Apply systemd units: `sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/`
5. Start services: `sudo systemctl daemon-reload && sudo systemctl enable --now agency agency-backup.timer`
