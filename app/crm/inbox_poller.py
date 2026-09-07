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

    async def poll_gmail(self, session: AsyncSession) -> List[Reply]:
        """
        Polls Gmail API for unread incoming messages using read-only scope,
        matches threadId, In-Reply-To, or sender to existing outreach,
        and triggers reply classification.
        """
        if not getattr(settings, "GMAIL_REFRESH_TOKEN", None) or not getattr(settings, "GMAIL_CLIENT_ID", None):
            return []

        from app.outreach.providers.gmail_oauth_provider import GmailOAuthEmailProvider
        provider = GmailOAuthEmailProvider()

        def _sync_fetch_gmail() -> List[Dict[str, Any]]:
            messages = []
            try:
                unread_items = provider.list_unread_messages(max_results=20)
                for item in unread_items:
                    m_id = item.get("id")
                    if not m_id:
                        continue
                    parsed = provider.get_message_detail(m_id)
                    if parsed:
                        messages.append(parsed)
            except Exception as e:
                logger.warning(f"[InboxPoller] Gmail API polling error: {e}")
            return messages

        raw_msgs = await asyncio.to_thread(_sync_fetch_gmail)
        processed: List[Reply] = []

        for m in raw_msgs:
            reply = await self.process_inbound_message(
                session=session,
                sender_email=m["sender_email"],
                subject=m["subject"],
                body=m["body"],
                in_reply_to=m.get("in_reply_to"),
                references=m.get("references"),
                thread_id=m.get("threadId"),
                message_id_header=m.get("message_id")
            )
            if reply:
                processed.append(reply)

        return processed

    async def poll_inbox(self, session: AsyncSession) -> List[Reply]:
        """
        Polls configured inbox (Gmail OAuth or IMAP) for unread incoming messages.
        In DRY_RUN or if unconfigured, logs idle status gracefully.
        """
        # 1. Prefer Gmail OAuth if configured
        is_gmail = (settings.EMAIL_PROVIDER or "").lower().strip() in ("gmail", "gmail_oauth") or getattr(settings, "GMAIL_REFRESH_TOKEN", None)
        if is_gmail and getattr(settings, "GMAIL_CLIENT_ID", None) and getattr(settings, "GMAIL_REFRESH_TOKEN", None):
            return await self.poll_gmail(session)

        # 2. Fall back to IMAP
        if settings.DRY_RUN or not settings.IMAP_HOST or not settings.IMAP_USER:
            logger.debug("[InboxPoller] Inbox polling skipped (unconfigured or DRY_RUN active).")
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
                    in_reply_to = _clean_header(msg.get("In-Reply-To"))
                    references = _clean_header(msg.get("References"))
                    msg_id_hdr = _clean_header(msg.get("Message-ID"))

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
                        "body": body,
                        "in_reply_to": in_reply_to,
                        "references": references,
                        "message_id": msg_id_hdr
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
                body=m["body"],
                in_reply_to=m.get("in_reply_to"),
                references=m.get("references"),
                message_id_header=m.get("message_id")
            )
            if reply:
                processed.append(reply)

        return processed

    async def process_inbound_message(
        self,
        session: AsyncSession,
        sender_email: str,
        subject: str,
        body: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        thread_id: Optional[str] = None,
        message_id_header: Optional[str] = None
    ) -> Optional[Reply]:
        """
        Matches an incoming email to an active Business / OutreachMessage,
        using threadId, Message-ID, In-Reply-To, References, or sender email,
        and triggers reply classification, follow-up cancellation, and CRM progression.
        """
        from app.database.models import OutreachEvent

        clean_sender = sender_email.lower().strip()
        if not clean_sender:
            return None

        outreach_msg = None

        # 1. Thread matching by Gmail threadId or In-Reply-To/References in OutreachEvent details
        if thread_id or in_reply_to or references:
            events_q = select(OutreachEvent).order_by(OutreachEvent.created_at.desc()).limit(100)
            recent_events = (await session.execute(events_q)).scalars().all()
            for ev in recent_events:
                ev_details = ev.details or {}
                if thread_id and ev_details.get("gmail_thread_id") == thread_id:
                    outreach_msg = await session.get(OutreachMessage, ev.outreach_message_id)
                    if outreach_msg:
                        break
                if in_reply_to and (
                    ev_details.get("message_id_header") == in_reply_to or
                    ev_details.get("gmail_message_id") == in_reply_to
                ):
                    outreach_msg = await session.get(OutreachMessage, ev.outreach_message_id)
                    if outreach_msg:
                        break
                if references and ev_details.get("message_id_header") and ev_details.get("message_id_header") in references:
                    outreach_msg = await session.get(OutreachMessage, ev.outreach_message_id)
                    if outreach_msg:
                        break

        # 2. Fallback to matching by recipient email
        if not outreach_msg:
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
        logger.info(f"[InboxPoller] Processed inbound reply for {biz.name} ({clean_sender}) [Thread: {thread_id}]: {reply.classification}")
        return reply

inbox_poller = InboxPoller()
