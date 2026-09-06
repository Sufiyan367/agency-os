"""
Phase 8 Production Data Platform & Database Hardening Tests.
Verifies:
- Dual SQLite / PostgreSQL engine abstraction & URL normalization
- Atomic transaction context manager (commit and rollback)
- Exact financial precision (Numeric(12, 2, asdecimal=False))
- Database-level webhook idempotency and replay protection
- Security audit logging with credential sanitization
- Safe health telemetry (dialect, latency, pool stats, no leaked secrets)
- Automated backup creation, integrity check, and disaster recovery SLAs
"""

import pytest
import uuid
import json
import hmac
import hashlib
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.api.app import app
from app.core.config import settings
from app.database.connection import (
    AsyncSessionLocal, init_db, normalize_database_url,
    get_database_dialect, check_database_connectivity,
    atomic_transaction, create_agency_engine
)
from app.database.models import (
    Business, Offer, Proposal, Deal, Payment, Customer,
    PaymentWebhookEvent, SecurityAuditLog, PipelineStage
)
from app.services.audit_service import AuditService, sanitize_audit_payload
from app.services.health_service import ProductionHealthService
from app.database.backup import backup_manager, DatabaseBackupManager
from app.payments.razorpay import razorpay_payment_provider


@pytest.mark.asyncio
async def test_database_url_normalization_and_engine_config():
    """Verifies PostgreSQL and SQLite URL normalization and engine pooling parameters."""
    # SQLite normalization
    assert normalize_database_url("sqlite:///app.db") == "sqlite+aiosqlite:///app.db"
    assert normalize_database_url("sqlite+aiosqlite:///app.db") == "sqlite+aiosqlite:///app.db"

    # PostgreSQL normalization
    assert normalize_database_url("postgresql://user:pass@localhost:5432/db") == "postgresql+asyncpg://user:pass@localhost:5432/db"
    assert normalize_database_url("postgres://user:pass@localhost:5432/db") == "postgresql+asyncpg://user:pass@localhost:5432/db"
    assert normalize_database_url("postgresql+asyncpg://user:pass@localhost:5432/db") == "postgresql+asyncpg://user:pass@localhost:5432/db"

    # Engine factory config validation
    pg_engine = create_agency_engine("postgresql+asyncpg://mock_user:mock_pass@127.0.0.1:5432/mock_db")
    assert pg_engine.dialect.name == "postgresql"
    assert pg_engine.pool.size() == settings.DB_POOL_SIZE
    await pg_engine.dispose()


@pytest.mark.asyncio
async def test_dialect_detection_and_connectivity_telemetry():
    """Verifies safe health telemetry exposes latency and dialect without credential leakage."""
    await init_db()
    dialect = get_database_dialect()
    assert dialect in ("sqlite", "postgresql")

    conn_info = await check_database_connectivity()
    assert conn_info["connected"] is True
    assert conn_info["dialect"] == dialect
    assert conn_info["latency_ms"] >= 0.0
    assert "password" not in json.dumps(conn_info).lower()
    assert "token" not in json.dumps(conn_info).lower()


@pytest.mark.asyncio
async def test_atomic_transaction_context_manager():
    """Verifies atomic_transaction commits on success and completely rolls back on failure."""
    await init_db()
    uid = uuid.uuid4().hex[:8]

    # Success case: Committed
    async with AsyncSessionLocal() as session:
        async with atomic_transaction(session):
            b1 = Business(
                name=f"Atomic Success {uid}",
                domain=f"success-{uid}.com",
                country="US",
                niche="HVAC"
            )
            session.add(b1)

    async with AsyncSessionLocal() as session:
        found = (await session.execute(
            select(Business).where(Business.domain == f"success-{uid}.com")
        )).scalars().first()
        assert found is not None
        assert found.name == f"Atomic Success {uid}"

    # Failure case: Rolled back cleanly
    with pytest.raises(ValueError, match="Simulated crash"):
        async with AsyncSessionLocal() as session:
            async with atomic_transaction(session):
                b2 = Business(
                    name=f"Atomic Rollback {uid}",
                    domain=f"rollback-{uid}.com",
                    country="US",
                    niche="HVAC"
                )
                session.add(b2)
                await session.flush()
                raise ValueError("Simulated crash")

    async with AsyncSessionLocal() as session:
        not_found = (await session.execute(
            select(Business).where(Business.domain == f"rollback-{uid}.com")
        )).scalars().first()
        assert not_found is None


@pytest.mark.asyncio
async def test_exact_financial_precision():
    """Verifies Numeric(12, 2, asdecimal=False) preserves exact cents and allows direct float comparisons."""
    await init_db()
    uid = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        async with atomic_transaction(session):
            biz = Business(
                name=f"Precision Dental {uid}",
                domain=f"precision-{uid}.com",
                country="US",
                niche="Dental"
            )
            session.add(biz)
            await session.flush()

            offer = Offer(
                business_id=biz.id,
                service_type="lead_gen",
                title="Exact Precision Offer",
                suggested_price_min=500.25,
                suggested_price_max=1250.75,
                recommended_price=875.50
            )
            session.add(offer)

            prop = Proposal(
                business_id=biz.id,
                title="Commercial Proposal",
                total_value=1250.75,
                advance_required=500.30,
                advance_received=500.30,
                remaining_balance=750.45
            )
            session.add(prop)

    async with AsyncSessionLocal() as session:
        saved_offer = (await session.execute(
            select(Offer).where(Offer.business_id == biz.id)
        )).scalars().first()
        assert saved_offer is not None
        # Float comparisons with no type error
        assert saved_offer.recommended_price >= 500.0
        assert saved_offer.recommended_price == 875.50
        assert saved_offer.suggested_price_min == 500.25
        assert saved_offer.suggested_price_max == 1250.75

        saved_prop = (await session.execute(
            select(Proposal).where(Proposal.business_id == biz.id)
        )).scalars().first()
        assert saved_prop is not None
        assert saved_prop.total_value == 1250.75
        assert saved_prop.advance_required == 500.30
        assert saved_prop.remaining_balance == 750.45


@pytest.mark.asyncio
async def test_database_level_webhook_idempotency():
    """Verifies PaymentWebhookEvent table enforces unique (provider, event_id) and route idempotency."""
    await init_db()
    test_secret = "test_rzp_sec_idemp"
    razorpay_payment_provider.webhook_secret = test_secret

    uid = uuid.uuid4().hex[:8]
    test_domain = f"idemp-{uid}.com"

    async with AsyncSessionLocal() as session:
        async with atomic_transaction(session):
            biz = Business(
                name=f"Idempotency Test {uid}",
                domain=test_domain,
                country="US",
                niche="Roofing",
                pipeline_stage=PipelineStage.PROPOSAL.value
            )
            session.add(biz)
            await session.flush()
            biz_id = biz.id

    webhook_payload = {
        "id": f"evt_rzp_idemp_{uid}",
        "event": "payment_link.paid",
        "created_at": 1710002000,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": f"plink_idemp_{uid}",
                    "amount": 75000,
                    "amount_paid": 75000,
                    "notes": {"business_id": str(biz_id)}
                }
            },
            "payment": {
                "entity": {
                    "id": f"pay_idemp_{uid}",
                    "amount": 75000,
                    "email": f"billing@{test_domain}"
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    valid_sig = hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First Delivery: Success
        r1 = await client.post(
            "/api/webhooks/razorpay",
            content=payload_bytes,
            headers={"X-Razorpay-Signature": valid_sig, "Content-Type": "application/json"}
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "SUCCESS"

        # Duplicate Delivery: Ignored by DB idempotency
        r2 = await client.post(
            "/api/webhooks/razorpay",
            content=payload_bytes,
            headers={"X-Razorpay-Signature": valid_sig, "Content-Type": "application/json"}
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "DUPLICATE_IGNORED"

    # Verify event record in database
    async with AsyncSessionLocal() as session:
        evt = (await session.execute(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider == "razorpay",
                PaymentWebhookEvent.event_id == f"evt_rzp_idemp_{uid}"
            )
        )).scalars().first()
        assert evt is not None
        assert evt.processing_status == "PROCESSED"
        assert evt.outcome == "SUCCESS"

        # Direct database uniqueness constraint assertion
        duplicate_evt = PaymentWebhookEvent(
            provider="razorpay",
            event_id=f"evt_rzp_idemp_{uid}",
            event_type="payment_link.paid"
        )
        session.add(duplicate_evt)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_security_audit_logging_and_sanitization():
    """Verifies AuditService logs events with WHO, WHAT, WHEN, WHY, and RESULT, scrubbing secrets."""
    await init_db()
    uid = uuid.uuid4().hex[:8]

    dirty_payload = {
        "username": "admin",
        "password": "SuperSecretPassword123!",
        "api_key": "live_sec_key_xyz",
        "access_token": "bearer_token_abc",
        "metadata": {
            "sub_secret": "nested_secret",
            "safe_counter": 42
        }
    }

    # Test scrubber function
    sanitized = sanitize_audit_payload(dirty_payload)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["metadata"]["sub_secret"] == "[REDACTED]"
    assert sanitized["metadata"]["safe_counter"] == 42

    # Test AuditService.log_event
    async with AsyncSessionLocal() as session:
        async with atomic_transaction(session):
            entry = await AuditService.log_event(
                db=session,
                actor=f"operator_{uid}",
                action="proposal.approved",
                entity_type="proposal",
                entity_id="999",
                reason="Client agreed to terms via recorded phone consultation",
                result="SUCCESS",
                details=dirty_payload,
                ip_address="192.168.1.100"
            )
            assert entry.id is not None

    # Query back
    async with AsyncSessionLocal() as session:
        logs = await AuditService.get_recent_logs(
            db=session,
            limit=10,
            action="proposal.approved",
            actor=f"operator_{uid}"
        )
        assert len(logs) >= 1
        log = logs[0]
        assert log.actor == f"operator_{uid}"
        assert log.action == "proposal.approved"
        assert log.entity_type == "proposal"
        assert log.entity_id == "999"
        assert log.result == "SUCCESS"
        assert log.details_json["password"] == "[REDACTED]"
        assert log.ip_address == "192.168.1.100"


@pytest.mark.asyncio
async def test_health_service_production_telemetry():
    """Verifies ProductionHealthService reports database status, latency, and safe telemetry."""
    report = await ProductionHealthService.check_system_health()
    assert report.database.status == "READY"
    assert "Dialect:" in report.database.details
    assert "Latency:" in report.database.details
    assert report.webhooks.status == "READY"


def test_backup_manager_integrity_and_disaster_recovery_slas():
    """Verifies DatabaseBackupManager creates verified backups and exports RPO/RTO SLA procedures."""
    # Test RPO/RTO recovery procedures metadata
    procedures = backup_manager.get_recovery_procedures()
    assert procedures["rpo_target_minutes"] == 60
    assert procedures["rto_target_minutes"] == 15
    assert "sqlite_restore_procedure" in procedures
    assert "postgres_restore_procedure" in procedures

    # Test backup creation
    res = backup_manager.create_backup()
    assert res["success"] is True
    assert res["integrity_verified"] is True
    assert res["compressed_bytes"] > 0
    assert res["filename"].endswith(".db.gz")
