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

    def __init__(self):
        self._processed_message_ids: set = set()

    def is_message_processed(self, message_id: Optional[str]) -> bool:
        """Checks if a message ID has already been ingested in this worker session."""
        if not message_id:
            return False
        return message_id in self._processed_message_ids

    def mark_message_processed(self, message_id: Optional[str]) -> None:
        """Registers a message ID as processed in memory."""
        if message_id:
            self._processed_message_ids.add(message_id)

    async def poll_gmail(self, session: AsyncSession) -> List[Reply]:
        """
        Polls Gmail API for unread incoming messages using read-only scope,
        matches threadId, In-Reply-To, or sender to existing outreach,
        and triggers reply classification.
        """
        if not getattr(settings, "GMAIL_REFRESH_TOKEN", None) or not getattr(settings, "GMAIL_CLIENT_ID", None):
            return []

        try:
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
                        if self.is_message_processed(m_id):
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
                    message_id_header=m.get("message_id"),
                    gmail_message_id=m.get("id")
                )
                if reply:
                    processed.append(reply)

            return processed
        except Exception as e:
            logger.warning(f"[InboxPoller] poll_gmail error: {e}")
            return []

    async def poll_inbox(self, session: AsyncSession) -> List[Reply]:
        """
        Polls configured inbox (Gmail OAuth or IMAP) for unread incoming messages.
        In DRY_RUN or if unconfigured, logs idle status gracefully.
        Fails safely on network or provider errors without crashing the caller.
        """
        try:
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
        except Exception as e:
            logger.warning(f"[InboxPoller] poll_inbox error: {e}")
            return []

    async def process_inbound_message(
        self,
        session: AsyncSession,
        sender_email: str,
        subject: str,
        body: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        thread_id: Optional[str] = None,
        message_id_header: Optional[str] = None,
        gmail_message_id: Optional[str] = None
    ) -> Optional[Reply]:
        """
        Matches an incoming email to an active Business / OutreachMessage,
        using threadId, Message-ID, In-Reply-To, References, or sender email,
        and triggers reply classification, follow-up cancellation, and CRM progression.
        Guarantees idempotency and avoids duplicate processing.
        """
        from app.database.models import OutreachEvent

        clean_sender = sender_email.lower().strip()
        if not clean_sender:
            return None

        # 1. In-memory duplicate check
        if gmail_message_id and self.is_message_processed(gmail_message_id):
            logger.info(f"[InboxPoller] Duplicate message detected in-memory (gmail_message_id={gmail_message_id}). Skipping.")
            return None
        if message_id_header and self.is_message_processed(message_id_header):
            logger.info(f"[InboxPoller] Duplicate message detected in-memory (message_id_header={message_id_header}). Skipping.")
            return None

        # 2. Database events duplicate check
        if gmail_message_id or message_id_header:
            events_q = select(OutreachEvent).where(
                OutreachEvent.event_type == "inbound_reply_received"
            ).order_by(OutreachEvent.created_at.desc()).limit(200)
            inbound_events = (await session.execute(events_q)).scalars().all()
            for ev in inbound_events:
                ev_details = ev.details or {}
                if gmail_message_id and ev_details.get("gmail_message_id") == gmail_message_id:
                    self.mark_message_processed(gmail_message_id)
                    logger.info(f"[InboxPoller] Duplicate message detected in DB events (gmail_message_id={gmail_message_id}). Skipping.")
                    return None
                if message_id_header and ev_details.get("message_id_header") == message_id_header:
                    self.mark_message_processed(message_id_header)
                    logger.info(f"[InboxPoller] Duplicate message detected in DB events (message_id_header={message_id_header}). Skipping.")
                    return None

        outreach_msg = None
        biz = None

        # 3. Multi-tier thread matching by Gmail threadId, In-Reply-To, References in OutreachEvents
        if thread_id or in_reply_to or references:
            events_q = select(OutreachEvent).order_by(OutreachEvent.created_at.desc()).limit(200)
            recent_events = (await session.execute(events_q)).scalars().all()
            for ev in recent_events:
                ev_details = ev.details or {}
                if thread_id and (
                    ev_details.get("thread_id") == thread_id or
                    ev_details.get("gmail_thread_id") == thread_id
                ):
                    outreach_msg = await session.get(OutreachMessage, ev.outreach_message_id)
                    if outreach_msg:
                        break
                if in_reply_to and (
                    ev_details.get("message_id") == in_reply_to or
                    ev_details.get("gmail_message_id") == in_reply_to or
                    ev_details.get("message_id_header") == in_reply_to
                ):
                    outreach_msg = await session.get(OutreachMessage, ev.outreach_message_id)
                    if outreach_msg:
                        break
                if references and (
                    (ev_details.get("message_id") and ev_details.get("message_id") in references) or
                    (ev_details.get("message_id_header") and ev_details.get("message_id_header") in references)
                ):
                    outreach_msg = await session.get(OutreachMessage, ev.outreach_message_id)
                    if outreach_msg:
                        break

        # 3b. ProspectMemory lookup by thread_id if still unmatched
        if not outreach_msg and thread_id:
            from app.database.models import ProspectMemory
            q_pm = select(ProspectMemory).where(ProspectMemory.thread_id == thread_id).order_by(ProspectMemory.updated_at.desc())
            pm = (await session.execute(q_pm)).scalars().first()
            if pm and pm.business_id:
                q_msg = select(OutreachMessage).where(OutreachMessage.business_id == pm.business_id).order_by(OutreachMessage.created_at.desc())
                outreach_msg = (await session.execute(q_msg)).scalars().first()
                biz = await session.get(Business, pm.business_id)

        # 4. Fallback to matching by recipient email in OutreachMessage
        if not outreach_msg:
            q_msg = select(OutreachMessage).where(
                OutreachMessage.recipient_email.ilike(clean_sender)
            ).order_by(OutreachMessage.created_at.desc())
            outreach_msg = (await session.execute(q_msg)).scalars().first()

        # 4b. Fallback to matching by Contact record email
        if not biz and not outreach_msg:
            from app.database.models import Contact
            q_contact = select(Contact).where(Contact.email.ilike(clean_sender)).order_by(Contact.id.desc())
            matched_contact = (await session.execute(q_contact)).scalars().first()
            if matched_contact:
                biz = await session.get(Business, matched_contact.business_id)
                q_msg = select(OutreachMessage).where(OutreachMessage.business_id == matched_contact.business_id).order_by(OutreachMessage.created_at.desc())
                outreach_msg = (await session.execute(q_msg)).scalars().first()

        # 4c. Fallback to matching by Business public_email or domain
        if not biz:
            if outreach_msg:
                biz = await session.get(Business, outreach_msg.business_id)
            else:
                domain_part = clean_sender.split("@")[-1].lower() if "@" in clean_sender else ""
                q_biz = select(Business).where(
                    or_(
                        Business.public_email.ilike(clean_sender),
                        Business.domain.ilike(f"%{domain_part}%") if domain_part else False
                    )
                )
                biz = (await session.execute(q_biz)).scalars().first()
                if biz:
                    q_msg = select(OutreachMessage).where(OutreachMessage.business_id == biz.id).order_by(OutreachMessage.created_at.desc())
                    outreach_msg = (await session.execute(q_msg)).scalars().first()

        if not biz:
            logger.info(f"[InboxPoller] Incoming email from {clean_sender} does not match any active lead. Ignoring (never create orphan business on inbound).")
            return None

        # 5. Database Reply check for identical content from same sender to same business
        existing_reply_q = select(Reply).where(
            Reply.business_id == biz.id,
            Reply.sender_email == clean_sender,
            Reply.raw_body == body
        )
        existing_reply = (await session.execute(existing_reply_q)).scalars().first()
        if existing_reply:
            logger.info(f"[InboxPoller] Duplicate reply detected in DB for business {biz.id} with identical content. Skipping.")
            if gmail_message_id:
                self.mark_message_processed(gmail_message_id)
            if message_id_header:
                self.mark_message_processed(message_id_header)
            return None

        # 6. Process through reply classifier
        reply = await reply_classifier.process_incoming_reply(
            session=session,
            business_id=biz.id,
            sender_email=clean_sender,
            raw_body=body,
            message_id=outreach_msg.id if outreach_msg else None
        )

        # 7. Record event for persistent idempotency tracking
        if outreach_msg:
            inbound_event = OutreachEvent(
                outreach_message_id=outreach_msg.id,
                event_type="inbound_reply_received",
                details={
                    "gmail_message_id": gmail_message_id,
                    "message_id_header": message_id_header,
                    "thread_id": thread_id,
                    "sender_email": clean_sender,
                    "classification": reply.classification
                }
            )
            session.add(inbound_event)

        # 8. Sync ProspectMemory thread_id if available
        if thread_id:
            from app.database.models import ProspectMemory
            q_mem = select(ProspectMemory).where(ProspectMemory.business_id == biz.id)
            mem = (await session.execute(q_mem)).scalars().first()
            if mem and (not mem.thread_id or mem.thread_id.startswith("thread-")):
                mem.thread_id = thread_id
                mem.updated_at = datetime.utcnow()

        await session.commit()

        if gmail_message_id:
            self.mark_message_processed(gmail_message_id)
        if message_id_header:
            self.mark_message_processed(message_id_header)

        logger.info(f"[InboxPoller] Processed inbound reply for {biz.name} ({clean_sender}) [Thread: {thread_id}]: {reply.classification}")
        return reply

inbox_poller = InboxPoller()
