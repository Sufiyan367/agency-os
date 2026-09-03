import sqlite3

def inspect():
    conn = sqlite3.connect('agency.db')
    cursor = conn.cursor()
    tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'") if not row[0].startswith('sqlite')]
    print("Database Tables and Row Counts:")
    for t in sorted(tables):
        cnt = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {cnt}")
    
    # Check source distributions
    print("\nBusiness Sources:")
    for row in cursor.execute("SELECT source, COUNT(*) FROM businesses GROUP BY source").fetchall():
        print(f"  {row[0]}: {row[1]}")

    print("\nLocalBusiness Sources:")
    for row in cursor.execute("SELECT source, COUNT(*) FROM local_businesses GROUP BY source").fetchall():
        print(f"  {row[0]}: {row[1]}")

    print("\nProposals Mock Status:")
    for row in cursor.execute("SELECT is_mock, status, COUNT(*) FROM proposals GROUP BY is_mock, status").fetchall():
        print(f"  mock={row[0]}, status={row[1]}: {row[2]}")

if __name__ == "__main__":
    inspect()
