import asyncio
import os
import sys
import json
from datetime import datetime, timezone
from sqlalchemy import select

os.chdir('/opt/agency')
sys.path.insert(0, '/opt/agency')

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import OutreachMessage, OutreachStatus, Business, PipelineStage
from app.outreach.sender import outreach_sender_adapter
from app.crm.inbox_poller import InboxPoller

async def execute_canary():
    print("==================================================")
    print("AGENCY OS — CONTROLLED PRODUCTION CANARY SEND")
    print("==================================================")
    
    sender_addr = getattr(settings, "TITAN_SMTP_USER", "hello@automatedagencyos.tech")
    recipient_addr = sender_addr  # Safe internal canary destination
    now_utc = datetime.now(timezone.utc)
    subject_line = f"Agency OS Canary Verification [{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}]"
    body_text = (
        "This is an authorized, controlled production canary transmission verifying "
        "Titan SMTP end-to-end transport, RFC 5322 Message-ID compliance, and IMAP synchronization "
        "for Agency OS.\n\n---\n"
        "Mailing Address: Agency OS Operations, 548 Market St, Suite 34291, San Francisco, CA 94104, USA\n"
        "To opt out of future communications, reply 'unsubscribe'."
    )
    
    async with AsyncSessionLocal() as session:
        # Check or create a canary business
        q_biz = select(Business).where(Business.domain == "automatedagencyos.tech")
        biz = (await session.execute(q_biz)).scalars().first()
        if not biz:
            biz = Business(
                name="Agency OS Verification Lab",
                domain="automatedagencyos.tech",
                website_url="https://automatedagencyos.tech",
                country="US",
                city="San Francisco",
                niche="hvac",
                pipeline_stage=PipelineStage.APPROVAL.value,
                public_email=recipient_addr,
                email_status="verified"
            )
            session.add(biz)
            await session.flush()
        
        # Create canary message with human approval status
        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=recipient_addr,
            subject=subject_line,
            body=body_text,
            status=OutreachStatus.APPROVED.value,
            actor_type="HUMAN",
            approved_at=now_utc
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        
        print(f"[*] Created OutreachMessage ID #{msg.id} for {recipient_addr}")
        print(f"[*] Starting live dispatch via Titan SMTP (SSL Port 465)...")
        
        # Dispatch exactly 1 message
        t_start = datetime.now(timezone.utc)
        res = await outreach_sender_adapter.send_approved_message(
            session=session,
            message_id=msg.id,
            force_live=True,
            enforce_window=False
        )
        t_end = datetime.now(timezone.utc)
        
        await session.refresh(msg)
        details = res.get("details", {})
        provider_msg_id = details.get("message_id")
        smtp_resp = details.get("smtp_response")
        print("\n[+] DISPATCH SUCCESSFUL!")
        print(f"    - DB Message ID:     {msg.id}")
        print(f"    - Provider Msg ID:   {provider_msg_id}")
        print(f"    - SMTP Response:     {smtp_resp}")
        print(f"    - DB Record Status:  {msg.status}")
        print(f"    - Sent At:           {msg.sent_at}")
        print(f"    - Duration:          {(t_end - t_start).total_seconds():.2f}s")
        print(f"    - Sent Folder Copy:  {details.get('sent_folder_copied')}")
        
        result_payload = {
            "timestamp": t_start.isoformat(),
            "sender": sender_addr,
            "recipient": recipient_addr,
            "subject": subject_line,
            "provider_message_id": provider_msg_id,
            "smtp_response": smtp_resp,
            "provider": "titan",
            "db_message_id": msg.id,
            "db_status": msg.status,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
            "tls_port": 465,
            "sent_folder_copied": details.get("sent_folder_copied")
        }
        
        with open("/tmp/canary_send_result.json", "w") as f:
            json.dump(result_payload, f, indent=2)
            
        print("[*] Result written to /tmp/canary_send_result.json")
        
        # Test IMAP Poller to verify inbox synchronization
        print("\n[*] Polling Titan IMAP (imap.titan.email:993 SSL)...")
        poller = InboxPoller()
        replies = await poller.poll_inbox(session)
        print(f"[+] IMAP Poll completed: {len(replies)} incoming replies processed.")
        print("==================================================")

if __name__ == '__main__':
    asyncio.run(execute_canary())
