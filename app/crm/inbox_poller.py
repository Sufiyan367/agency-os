import asyncio
import email
from email.header import decode_header
import email.utils
import imaplib
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database.models import Business, OutreachMessage, Reply
from app.crm.reply_classifier import reply_classifier
from app.core.config import settings
from app.core.logging import logger

def _clean_header(val: Optional[str]) -> str:
    if not val:
        return ""
    decoded_parts = decode_header(val)
    out = []
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(part.decode("latin1", errors="replace"))
        else:
            out.append(str(part))
    return "".join(out)

class InboxPoller:
    """
    Ingests prospect replies via IMAP inbox polling and inbound email webhooks,
    matching incoming emails to existing outreach records and executing AI classification.
    """

    async def poll_inbox(self, session: AsyncSession) -> List[Reply]:
        """
        Polls IMAP server for unread incoming messages and processes replies.
        In DRY_RUN or if IMAP is unconfigured, logs idle status gracefully.
        """
        if settings.DRY_RUN or not settings.IMAP_HOST or not settings.IMAP_USER:
            logger.debug("[InboxPoller] IMAP polling skipped (unconfigured or DRY_RUN active).")
            return []

        def _sync_fetch_unseen() -> List[Dict[str, str]]:
            messages = []
            try:
                mail = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT, timeout=10)
                mail.login(settings.IMAP_USER, settings.IMAP_PASSWORD or "")
                mail.select("INBOX")
                status, search_data = mail.search(None, "UNSEEN")
                if status != "OK" or not search_data or not search_data[0]:
                    mail.close()
                    mail.logout()
                    return []

                msg_ids = search_data[0].split()
                for m_id in msg_ids[:20]:  # batch up to 20
                    res, data = mail.fetch(m_id, "(RFC822)")
                    if res != "OK" or not data:
                        continue
                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    from_hdr = _clean_header(msg.get("From"))
                    _, sender_email = email.utils.parseaddr(from_hdr)
                    subject = _clean_header(msg.get("Subject"))

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            ctype = part.get_content_type()
                            cdispo = str(part.get("Content-Disposition"))
                            if ctype == "text/plain" and "attachment" not in cdispo:
                                body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")

                    messages.append({
                        "sender_email": sender_email.lower().strip(),
                        "subject": subject,
                        "body": body
                    })
                    # Mark as read
                    mail.store(m_id, "+FLAGS", "\\Seen")

                mail.close()
                mail.logout()
            except Exception as e:
                logger.warning(f"[InboxPoller] IMAP connection error: {e}")
            return messages

        raw_msgs = await asyncio.to_thread(_sync_fetch_unseen)
        processed: List[Reply] = []

        for m in raw_msgs:
            reply = await self.process_inbound_message(
                session=session,
                sender_email=m["sender_email"],
                subject=m["subject"],
                body=m["body"]
            )
            if reply:
                processed.append(reply)

        return processed

    async def process_inbound_message(
        self,
        session: AsyncSession,
        sender_email: str,
        subject: str,
        body: str
    ) -> Optional[Reply]:
        """
        Matches an incoming email to an active Business / OutreachMessage,
        and triggers reply classification, follow-up cancellation, and CRM progression.
        """
        clean_sender = sender_email.lower().strip()
        if not clean_sender:
            return None

        # Look up business by public_email or recent outreach message
        q_msg = select(OutreachMessage).where(
            OutreachMessage.recipient_email.ilike(clean_sender)
        ).order_by(OutreachMessage.created_at.desc())
        outreach_msg = (await session.execute(q_msg)).scalars().first()

        biz = None
        if outreach_msg:
            biz = await session.get(Business, outreach_msg.business_id)
        else:
            q_biz = select(Business).where(
                or_(
                    Business.public_email.ilike(clean_sender),
                    Business.domain.ilike(f"%{clean_sender.split('@')[-1]}%")
                )
            )
            biz = (await session.execute(q_biz)).scalars().first()

        if not biz:
            logger.info(f"[InboxPoller] Incoming email from {clean_sender} does not match any active lead. Ignoring.")
            return None

        # Process through reply classifier
        reply = await reply_classifier.process_incoming_reply(
            session=session,
            business_id=biz.id,
            sender_email=clean_sender,
            raw_body=body,
            message_id=outreach_msg.id if outreach_msg else None
        )
        logger.info(f"[InboxPoller] Processed inbound reply for {biz.name} ({clean_sender}): {reply.classification}")
        return reply

inbox_poller = InboxPoller()
