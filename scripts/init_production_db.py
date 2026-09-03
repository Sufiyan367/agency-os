import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from app.database.production_init import production_reset_service

def main():
    parser = argparse.ArgumentParser(description="Initialize clean production database for JARVIS // AG.")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating a backup before reset")
    parser.add_argument("--restore", type=str, help="Restore database from a specific backup file")

    args = parser.parse_args()

    if args.restore:
        print(f"\nRestoring database from: {args.restore}...")
        try:
            production_reset_service.restore_from_backup(args.restore)
            print("✓ Database restored successfully.")
        except Exception as e:
            print(f"✗ Restore failed: {e}")
            sys.exit(1)
        return

    print("==================================================")
    print(" JARVIS // AG — PRODUCTION DATABASE INITIALIZATION")
    print("==================================================")
    print("Preparing clean production database for FIRST REAL CLIENT...")
    
    res = production_reset_service.initialize_clean_production(create_backup=not args.no_backup)
    
    if res.get("backup_file"):
        print(f"✓ Archived existing database to: {res['backup_file']}")
    else:
        print("ℹ No previous database to archive (or backup skipped).")

    print("\nFresh Production Baseline Initialized:")
    print("--------------------------------------------------")
    for k, v in res["metrics"].items():
        print(f"  {k.replace('_', ' ').title()}: {v}")
    
    print("\nOperational Safeguards:")
    print("--------------------------------------------------")
    for k, v in res["safeguards"].items():
        print(f"  {k.replace('_', ' ').title()}: {v}")

    print("\nMode: FIRST CLIENT MODE (All outbound delivery & payments safely simulated)")
    print("==================================================\n")

if __name__ == "__main__":
    main()
