import os
import sqlite3

def run_migration():
    db_path = "/opt/agency/data/agency.db"
    if not os.path.exists(db_path):
        db_path = "agency.db"
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(outreach_messages)")
    cols = [c[1] for c in cur.fetchall()]
    print(f"Existing columns in outreach_messages on {db_path}: {len(cols)}")
    
    if "actor_type" not in cols:
        print("Adding column actor_type...")
        cur.execute("ALTER TABLE outreach_messages ADD COLUMN actor_type VARCHAR(50) DEFAULT 'HUMAN'")
        print("Added actor_type.")
    else:
        print("actor_type already present.")

    if "auto_approval_eligibility" not in cols:
        print("Adding column auto_approval_eligibility...")
        cur.execute("ALTER TABLE outreach_messages ADD COLUMN auto_approval_eligibility JSON")
        print("Added auto_approval_eligibility.")
    else:
        print("auto_approval_eligibility already present.")

    conn.commit()
    conn.close()
    print("MIGRATION_COMPLETE")

if __name__ == "__main__":
    run_migration()
