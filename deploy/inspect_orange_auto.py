import sys
import asyncio
import sqlite3

sys.path.insert(0, "/opt/agency")
from app.database.connection import AsyncSessionLocal
from app.database.models import OutreachMessage
from app.outreach.auto_approval import auto_approval_engine

async def check():
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

    async with AsyncSessionLocal() as session:
        msg = await session.get(OutreachMessage, 12)
        if not msg:
            print("Message 12 not found in AsyncSession")
            return
        res = await auto_approval_engine.evaluate_message_eligibility(session, msg)
        print("\n--- ELIGIBILITY EVALUATION FOR MESSAGE #12 ---")
        print("IS_ELIGIBLE:", res.is_eligible)
        print("BLOCKING REASONS:", res.blocking_reasons)
        print("CHECKS:")
        for c in res.checks:
            mark = "PASS" if c["passed"] else "FAIL"
            print(f"  [{mark}] {c['name']}: {c['detail']}")

if __name__ == "__main__":
    asyncio.run(check())

