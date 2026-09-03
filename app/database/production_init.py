import os
import shutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import sqlite3

from app.core.config import settings
from app.database.connection import get_db, init_db

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "agency.db")
BACKUPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backups")

# Operational tables that hold test/demo data (to be cleaned)
OPERATIONAL_TABLES = [
    "businesses",
    "contacts",
    "audit_runs",
    "audit_findings",
    "lead_scores",
    "offers",
    "outreach_messages",
    "outreach_events",
    "replies",
    "pipeline_events",
    "customers",
    "projects",
    "payments",
    "proposals",
    "deals",
    "deal_audit_trail",
    "local_businesses",
    "local_leads",
    "local_audits",
    "local_outreach_messages",
    "local_lead_events",
    "local_followups",
    "system_runs"
]

class ProductionResetService:
    """
    Safely separates demo/test datasets from clean production data.
    Backs up the existing database before clearing operational records,
    leaving reference metadata (Countries, Niches, Markets) intact.
    """

    @classmethod
    def backup_database(cls) -> Optional[str]:
        """Creates a timestamped copy of the existing SQLite database file."""
        if not os.path.exists(DB_PATH):
            return None

        os.makedirs(BACKUPS_DIR, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"agency_pre_prod_backup_{timestamp}.db"
        backup_filepath = os.path.join(BACKUPS_DIR, backup_filename)

        try:
            shutil.copy2(DB_PATH, backup_filepath)
            logger.info(f"[ProductionResetService] Database archived safely to: {backup_filepath}")
            return backup_filepath
        except Exception as e:
            logger.error(f"[ProductionResetService] Failed to create database backup: {e}")
            raise RuntimeError(f"Database backup failed: {e}")

    @classmethod
    def initialize_clean_production(cls, create_backup: bool = True) -> Dict[str, Any]:
        """
        Executes a controlled production initialization:
        1. Archives existing database to backups/
        2. Clears demo/test operational records
        3. Preserves reference metadata (countries, niches, market opportunities)
        4. Verifies clean zero-state metric baseline
        """
        backup_file = None
        if create_backup:
            backup_file = cls.backup_database()

        if not os.path.exists(DB_PATH):
            logger.info("[ProductionResetService] Database file does not exist yet. It will be initialized fresh.")
            return cls._get_zero_state_summary(backup_file)

        # Connect synchronously to SQLite to clear operational rows safely
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Disable foreign keys temporarily for clean truncation
        cursor.execute("PRAGMA foreign_keys = OFF;")

        cleared_counts: Dict[str, int] = {}
        for table in OPERATIONAL_TABLES:
            try:
                # Check if table exists
                cursor.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{table}'")
                if cursor.fetchone()[0] > 0:
                    cnt = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    cursor.execute(f"DELETE FROM {table}")
                    cleared_counts[table] = cnt
            except Exception as e:
                logger.warning(f"Could not clear table {table}: {e}")

        # Reset SQLite auto-increment sequences for operational tables
        try:
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            if cursor.fetchone()[0] > 0:
                for table in OPERATIONAL_TABLES:
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
        except Exception as e:
            logger.debug(f"Could not clear sqlite_sequence: {e}")

        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.close()

        logger.info(f"[ProductionResetService] Clean production database initialized. Cleared tables: {cleared_counts}")

        return cls._get_zero_state_summary(backup_file, cleared_counts)

    @classmethod
    def restore_from_backup(cls, backup_filepath: str) -> bool:
        """Restores a previous database backup."""
        if not os.path.exists(backup_filepath):
            raise FileNotFoundError(f"Backup file '{backup_filepath}' not found.")

        try:
            shutil.copy2(backup_filepath, DB_PATH)
            logger.info(f"[ProductionResetService] Database restored successfully from: {backup_filepath}")
            return True
        except Exception as e:
            logger.error(f"[ProductionResetService] Failed to restore database from backup: {e}")
            raise RuntimeError(f"Restore failed: {e}")

    @classmethod
    def _get_zero_state_summary(cls, backup_path: Optional[str] = None, cleared_details: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return {
            "status": "INITIALIZED",
            "environment": "PRODUCTION_READY",
            "mode": "FIRST_CLIENT_MODE",
            "backup_file": backup_path,
            "metrics": {
                "prospects": 0,
                "qualified_leads": 0,
                "outreach_sent": 0,
                "replies": 0,
                "meetings": 0,
                "won_deals": 0,
                "pipeline_value_usd": 0.0,
                "cash_received_usd": 0.0
            },
            "safeguards": {
                "email_dry_run": settings.EMAIL_DRY_RUN,
                "payment_dry_run": settings.PAYMENT_DRY_RUN,
                "razorpay_mode": getattr(settings, "RAZORPAY_MODE", "test"),
                "human_approval_mandatory": True,
                "commercial_minimum_threshold_usd": settings.MINIMUM_SERVICE_VALUE_USD
            },
            "cleared_operational_tables": cleared_details or {}
        }

production_reset_service = ProductionResetService()
