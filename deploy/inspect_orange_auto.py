import sqlite3

conn = sqlite3.connect("/opt/agency/data/agency.db")
cur = conn.cursor()

cur.execute("""
    SELECT id, business_id, recipient_email, subject, status, approved_at, sent_at, actor_type 
    FROM outreach_messages 
    WHERE recipient_email LIKE '%orange%' OR id = 12
""")
rows = cur.fetchall()
print("Found rows matching orange or id 12:")
for r in rows:
    print(r)

conn.close()
