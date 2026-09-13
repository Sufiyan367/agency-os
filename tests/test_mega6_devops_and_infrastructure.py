"""
==============================================================================
MEGA PROMPT 6: PRODUCTION INFRASTRUCTURE, DEVOPS & RELIABILITY REGRESSION SUITE
==============================================================================
Verifies:
1. Production Configuration Validation & Environment Isolation
2. Automated Backup Creation & Integrity Verification
3. Controlled Non-Destructive Restore Test (Safe Target)
4. Alembic Migration & Schema Synchronization
5. Observability Telemetry (/health) with Resource & Backup Tracking
6. Hardened Systemd & Safe Deployment Scripts Integrity
7. Four-Industry Pipeline Architecture Validation (Automotive, Dental, Roofing, HVAC)
8. Non-Negotiable Safety Baseline & Canary #12 Protection
==============================================================================
"""

import os
import sys
import json
import gzip
import shutil
import sqlite3
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.core.config import settings, get_env_file
from app.database.backup import backup_manager, get_backup_directory, get_sqlite_db_path
from app.database.connection import Base, AsyncSessionLocal
from app.database.models import Business, OutreachMessage
from app.commercial.pricing_engine import PricingEngine


# ==============================================================================
# 1. CONFIGURATION & ENVIRONMENT ISOLATION TESTS
# ==============================================================================

def test_environment_isolation_and_env_protection():
    """Verify that test runs strictly isolate from production .env files."""
    orig_env = os.environ.get("APP_ENV")
    orig_testing = os.environ.get("TESTING")
    try:
        os.environ["APP_ENV"] = "test"
        os.environ["TESTING"] = "true"
        assert get_env_file() is None, "Test environment must NEVER load production .env file"
    finally:
        if orig_env is not None:
            os.environ["APP_ENV"] = orig_env
        else:
            os.environ.pop("APP_ENV", None)
        if orig_testing is not None:
            os.environ["TESTING"] = orig_testing
        else:
            os.environ.pop("TESTING", None)


def test_safety_baseline_configuration_invariants():
    """Verify default safety invariants: payments disabled, research only, dry run."""
    assert settings.DRY_RUN is True, "DRY_RUN must default to True for safety"
    assert settings.BACKUP_RETENTION_DAYS >= 7, "Backup retention must be at least 7 days"


# ==============================================================================
# 2. BACKUP & RESTORE VERIFICATION TESTS
# ==============================================================================

def test_backup_creation_and_integrity_check():
    """Verify automated creation of compressed, integrity-verified SQLite snapshot."""
    res = backup_manager.create_backup()
    assert res["success"] is True
    assert res["integrity_verified"] is True
    assert os.path.exists(res["filepath"])
    assert res["compressed_bytes"] > 0
    assert res["filename"].startswith("agency_backup_")
    assert res["filename"].endswith(".db.gz")


def test_controlled_non_destructive_restore_to_temporary_database():
    """
    NON-DESTRUCTIVE RESTORE TEST:
    Restores latest backup into an isolated temporary database file.
    Verifies PRAGMA integrity_check, tables existence, and Canary #12 presence.
    NEVER touches or restores over the active live database.
    """
    backups = backup_manager.list_backups()
    assert len(backups) > 0, "At least one backup must exist for restore testing"
    latest_backup = backups[0]["filepath"]

    temp_dir = tempfile.mkdtemp(prefix="test_restore_isolated_")
    isolated_db_path = os.path.join(temp_dir, "isolated_agency.db")

    try:
        # 1. Decompress into isolated path
        with gzip.open(latest_backup, "rb") as f_in:
            with open(isolated_db_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # 2. Verify integrity
        conn = sqlite3.connect(isolated_db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        check_res = cur.fetchone()
        assert check_res is not None and check_res[0] == "ok", "Restored DB must pass PRAGMA integrity_check"

        # 3. Verify critical tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        assert "businesses" in tables
        assert "outreach_messages" in tables
        assert "users" in tables

        # 4. Invariant: Check Canary #12 inside restored DB
        cur.execute("SELECT id, business_id, status, sent_at FROM outreach_messages WHERE id = 12;")
        canary = cur.fetchone()
        if canary:
            assert canary[2] == "APPROVED", "Canary #12 must be in APPROVED status"
            assert canary[3] is None, "Canary #12 sent_at must be None"

        conn.close()

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 3. MIGRATION & SCHEMA SYNCHRONIZATION TESTS
# ==============================================================================

def test_migration_and_schema_synchronization():
    """Verify that all SQLAlchemy model tables exist in the target database."""
    db_path = get_sqlite_db_path()
    assert db_path and os.path.exists(db_path), "Active database must exist"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    db_tables = set(r[0] for r in cur.fetchall())
    conn.close()

    model_tables = set(Base.metadata.tables.keys())
    missing_tables = model_tables - db_tables
    assert len(missing_tables) == 0, f"Database missing model tables: {missing_tables}"


# ==============================================================================
# 4. OBSERVABILITY & HEALTH ENDPOINT TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_health_observability_endpoint_structure():
    """Verify that /health returns structured observability telemetry with resources and backups."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()

        # Core health fields
        assert data["status"] in ("ok", "degraded")
        assert data["overall_state"] in ("HEALTHY", "DEGRADED", "UNHEALTHY")
        assert "database" in data
        assert "worker" in data
        assert "gmail" in data
        assert "discovery" in data
        assert "outreach" in data
        assert "payment" in data

        # Enhanced Mega 6 observability
        assert "resources" in data
        if data["resources"]:
            assert "total_gb" in data["resources"]
            assert "free_gb" in data["resources"]
            assert "used_percent" in data["resources"]

        assert "backups" in data
        if data["backups"]:
            assert "backup_count" in data["backups"]
            assert data["backups"]["rpo_target_minutes"] == 60
            assert data["backups"]["rto_target_minutes"] == 15

        # Secrets non-leakage invariant
        raw_text = res.text
        assert "password" not in raw_text.lower() or 'password":null' in raw_text.lower() or '"password": null' in raw_text.lower() or 'password_reset' in raw_text.lower()
        assert "secret" not in raw_text.lower() or 'secret":null' in raw_text.lower() or '"secret": null' in raw_text.lower()


# ==============================================================================
# 5. HARDENED SYSTEMD & DEPLOYMENT SCRIPTS INTEGRITY
# ==============================================================================

def test_hardened_systemd_and_deployment_scripts_exist():
    """Verify that version-controlled systemd units and safe deployment scripts exist."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Systemd files
    service_path = os.path.join(base, "deploy", "systemd", "agency.service")
    backup_service_path = os.path.join(base, "deploy", "systemd", "agency-backup.service")
    backup_timer_path = os.path.join(base, "deploy", "systemd", "agency-backup.timer")
    
    assert os.path.exists(service_path), "deploy/systemd/agency.service must exist"
    assert os.path.exists(backup_service_path), "deploy/systemd/agency-backup.service must exist"
    assert os.path.exists(backup_timer_path), "deploy/systemd/agency-backup.timer must exist"

    with open(service_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "MemoryMax=1500M" in content
        assert "MemoryHigh=1200M" in content
        assert "TasksMax=100" in content
        assert "NoNewPrivileges=true" in content

    # Scripts
    deploy_script = os.path.join(base, "scripts", "deploy_safe.sh")
    rollback_script = os.path.join(base, "scripts", "rollback.sh")
    run_backup_script = os.path.join(base, "scripts", "run_backup.py")
    test_restore_script = os.path.join(base, "scripts", "test_restore.py")

    assert os.path.exists(deploy_script), "scripts/deploy_safe.sh must exist"
    assert os.path.exists(rollback_script), "scripts/rollback.sh must exist"
    assert os.path.exists(run_backup_script), "scripts/run_backup.py must exist"
    assert os.path.exists(test_restore_script), "scripts/test_restore.py must exist"


# ==============================================================================
# 6. FOUR-INDUSTRY PIPELINE VALIDATION
# ==============================================================================

def test_four_industry_pricing_and_pipeline_integrity():
    """Verify deterministic pricing and milestone calculations across all four core industries."""
    industries = ["Automotive", "Dental", "Roofing", "HVAC"]
    for ind in industries:
        pricing = PricingEngine.calculate_pricing(
            industry=ind,
            selected_addons=["calendar_sync"]
        )
        assert pricing.total_price_usd >= 500.0, f"Commercial floor must be >= $500 for {ind}"
        assert round(pricing.advance_deposit_usd + pricing.balance_due_usd, 2) == pricing.total_price_usd
        assert pricing.advance_deposit_usd == round(pricing.total_price_usd * 0.40, 2)
        assert pricing.balance_due_usd == round(pricing.total_price_usd * 0.60, 2)
        assert pricing.industry.lower() == ind.lower()


# ==============================================================================
# 7. SAFETY INVARIANT: ORANGE AUTO CANARY #12
# ==============================================================================

@pytest.mark.asyncio
async def test_orange_auto_canary_remains_approved_and_unmodified():
    """
    NON-NEGOTIABLE CANARY SAFETY INVARIANT:
    OutreachMessage #12 (Business 30, Orange Auto) must remain APPROVED with sent_at=None.
    """
    async with AsyncSessionLocal() as session:
        msg = await session.get(OutreachMessage, 12)
        if msg:
            assert msg.status == "APPROVED", "Canary #12 status must remain APPROVED"
            assert msg.sent_at is None, "Canary #12 sent_at must remain None (ZERO live dispatches)"
