#!/usr/bin/env python3
"""
Migration & Schema Synchronization Verifier for Agency OS.
Audits the Alembic migration history, verifies table registration against Base.metadata,
and confirms schema synchronization without modifying data.
"""
import sys
import os
import json
import sqlite3
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database.backup import get_sqlite_db_path
from app.database.connection import Base
import app.database.models
import app.database.ml_models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MigrationVerifier] %(message)s"
)
logger = logging.getLogger("MigrationVerifier")


def verify_migrations() -> int:
    db_path = get_sqlite_db_path()
    if not db_path or not os.path.exists(db_path):
        logger.error(f"Database not found at: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Check alembic_version table
        cursor.execute("SELECT version_num FROM alembic_version;")
        row = cursor.fetchone()
        current_version = row[0] if row else "NONE"
        logger.info(f"Current Alembic revision in database: {current_version}")

        # 2. Compare existing SQLite tables with registered SQLAlchemy models
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        db_tables = set(r[0] for r in cursor.fetchall())
        model_tables = set(Base.metadata.tables.keys())

        missing_in_db = model_tables - db_tables
        extra_in_db = db_tables - model_tables

        logger.info(f"Registered SQLAlchemy models count: {len(model_tables)}")
        logger.info(f"Database tables count: {len(db_tables)}")

        status_ok = (len(missing_in_db) == 0)

        result = {
            "alembic_version": current_version,
            "database_tables_count": len(db_tables),
            "registered_models_count": len(model_tables),
            "missing_in_database": list(missing_in_db),
            "extra_tables_in_database": [t for t in extra_in_db if t != "alembic_version"],
            "schema_synchronized": status_ok
        }

        print(json.dumps(result, indent=2))

        if not status_ok:
            logger.error(f"Schema mismatch! Missing tables in DB: {missing_in_db}")
            return 1

        logger.info("All model tables exist in database. Schema is synchronized.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(verify_migrations())
