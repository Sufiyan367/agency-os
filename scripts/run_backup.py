#!/usr/bin/env python3
"""
Automated Database Backup Runner for Agency OS.
Executes an online, integrity-verified, gzip-compressed snapshot of the SQLite database.
Enforces retention policy and logs structured backup telemetry.
"""
import sys
import os
import json
import logging
from datetime import datetime

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database.backup import backup_manager
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [BackupRunner] %(message)s"
)
logger = logging.getLogger("BackupRunner")


def run_backup():
    logger.info("Initiating scheduled database backup...")
    try:
        result = backup_manager.create_backup()
        logger.info(
            f"Backup SUCCESS: {result['filename']} | "
            f"Original: {result['original_bytes']:,} bytes | "
            f"Compressed: {result['compressed_bytes']:,} bytes ({result['compression_savings']}) | "
            f"Integrity: {result['integrity_verified']}"
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        logger.error(f"Backup FAILED: {e}", exc_info=True)
        print(json.dumps({"success": False, "error": str(e), "timestamp": datetime.utcnow().isoformat()}))
        return 1


if __name__ == "__main__":
    sys.exit(run_backup())
