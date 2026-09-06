"""
Audit Service for Enterprise Security and Operational Telemetry.
Records WHO, WHAT, WHEN, WHY, and RESULT without credential leakage.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database.models import SecurityAuditLog
from app.core.logging import logger

SENSITIVE_KEYS = {
    "password", "password_hash", "token", "access_token", "refresh_token",
    "secret", "api_key", "secret_key", "authorization", "auth",
    "card", "cvv", "pan", "signature"
}


def sanitize_audit_payload(data: Any) -> Any:
    """
    Recursively sanitize dictionaries and lists to scrub any sensitive credentials.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, val in data.items():
            key_lower = str(key).lower()
            if any(sens in key_lower for sens in SENSITIVE_KEYS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(val, (dict, list)):
                sanitized[key] = sanitize_audit_payload(val)
            else:
                sanitized[key] = val
        return sanitized
    elif isinstance(data, list):
        return [sanitize_audit_payload(item) for item in data]
    return data


class AuditService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        reason: Optional[str] = None,
        result: str = "SUCCESS",
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> SecurityAuditLog:
        """
        Record an auditable security or operational event to the database.
        """
        clean_details = sanitize_audit_payload(details or {})
        
        audit_entry = SecurityAuditLog(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            reason=reason,
            result=result,
            details_json=clean_details,
            ip_address=ip_address,
            created_at=datetime.utcnow()
        )
        
        try:
            db.add(audit_entry)
            await db.flush()
            logger.info(
                f"[AUDIT] actor={actor} action={action} entity={entity_type}:{entity_id} "
                f"result={result} reason={reason}"
            )
        except Exception as e:
            logger.error(f"Failed to persist audit entry for action '{action}': {e}")
            raise
            
        return audit_entry

    @staticmethod
    async def get_recent_logs(
        db: AsyncSession,
        limit: int = 50,
        action: Optional[str] = None,
        actor: Optional[str] = None
    ) -> List[SecurityAuditLog]:
        """
        Retrieve recent audit logs with optional filters.
        """
        stmt = select(SecurityAuditLog).order_by(desc(SecurityAuditLog.created_at)).limit(limit)
        if action:
            stmt = stmt.where(SecurityAuditLog.action == action)
        if actor:
            stmt = stmt.where(SecurityAuditLog.actor == actor)
            
        res = await db.execute(stmt)
        return list(res.scalars().all())
