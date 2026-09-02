import hmac
import hashlib
import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import Business, Offer, Customer, Project, Payment, PipelineStage
from app.payments.razorpay import RazorpayPaymentProvider, razorpay_payment_provider
from app.payments.provider import get_active_payment_provider
from app.core.config import settings

@pytest.mark.asyncio
async def test_razorpay_payment_link_generation_dry_run():
    provider = RazorpayPaymentProvider()
    res = await provider.create_payment_link(
        business_id=101,
        offer_id=202,
        title="SEO & Performance Turnaround Package",
        amount_usd=750.0,
        customer_name="John Doe",
        customer_email="john@example.com"
    )

    assert res["status"] == "created"
    assert res["provider"] == "razorpay"
    assert res["amount"] == 750.0
    assert res["currency"] in ("USD", "INR")
    assert res["checkout_url"].startswith("https://rzp.io/i/")
    assert res["payment_link_id"].startswith("plink_test_")
    assert res["mode"] == "dry_run"

def test_razorpay_webhook_signature_verification():
    secret = "rzp_webhook_secret_key_12345"
    provider = RazorpayPaymentProvider(webhook_secret=secret)
    payload = b'{"event":"payment_link.paid","payload":{"entity":{"id":"plink_123"}}}'

    # 1. Valid HMAC-SHA256 signature
    valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    is_valid, msg = provider.verify_webhook_signature(payload, valid_sig)
    assert is_valid is True
    assert msg == "Valid signature"

    # 2. Tampered signature
    bad_sig = "deadbeef" + valid_sig[8:]
    is_valid, msg = provider.verify_webhook_signature(payload, bad_sig)
    assert is_valid is False
    assert "mismatch" in msg

    # 3. Missing header
    is_valid, msg = provider.verify_webhook_signature(payload, None)
    assert is_valid is False
    assert "Missing" in msg

@pytest.mark.asyncio
async def test_razorpay_webhook_payment_link_paid_advances_to_won_and_onboards():
    await init_db()
    test_secret = "test_rzp_sec_xyz"

    uid = uuid.uuid4().hex[:6]
    test_domain = f"apexdental-{uid}.com"

    async with AsyncSessionLocal() as session:
        # Create test business and offer
        biz = Business(
            name="Apex Dental Care",
            domain=test_domain,
            phone="+1-555-321-7654",
            public_email=f"billing@{test_domain}",
            city="Austin",
            country="US",
            niche="Dentistry",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.flush()

        offer = Offer(
            business_id=biz.id,
            service_type="web_turnaround",
            title="Comprehensive Web & SEO Optimization",
            recommended_price=850.0,
            deliverables=["Core Web Vitals Remediation", "Local SEO Injection", "Mobile Booking Setup"]
        )
        session.add(offer)
        await session.commit()
        await session.refresh(biz)
        biz_id = biz.id

    # Configure mock webhook secret on provider
    razorpay_payment_provider.webhook_secret = test_secret

    webhook_payload = {
        "event": "payment_link.paid",
        "created_at": 1710000000,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_apex_9988",
                    "amount": 85000,
                    "amount_paid": 85000,
                    "currency": "USD",
                    "status": "paid",
                    "notes": {
                        "business_id": str(biz_id)
                    },
                    "customer": {
                        "name": "Apex Dental",
                        "email": "billing@apexdentalcare.com"
                    }
                }
            },
            "payment": {
                "entity": {
                    "id": f"pay_rzp_apex_{uid}",
                    "amount": 85000,
                    "currency": "USD",
                    "status": "captured",
                    "email": "billing@apexdentalcare.com"
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    valid_sig = hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/webhooks/razorpay",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": valid_sig
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["business_id"] == biz_id

    # Verify Database state
    async with AsyncSessionLocal() as session:
        updated_biz = await session.get(Business, biz_id)
        assert updated_biz.pipeline_stage == PipelineStage.WON.value

        cust = (await session.execute(
            select(Customer).where(Customer.business_id == biz_id)
        )).scalars().first()
        assert cust is not None
        assert cust.company_name == "Apex Dental Care"

        proj = (await session.execute(
            select(Project).where(Project.customer_id == cust.id)
        )).scalars().first()
        assert proj is not None
        assert proj.status in ("IN_PROGRESS", "ACTIVE")

        pmt = (await session.execute(
            select(Payment).where(Payment.reference_id == f"pay_rzp_apex_{uid}")
        )).scalars().first()
        assert pmt is not None
        assert pmt.amount == 850.0
        assert pmt.status == "COMPLETED"

@pytest.mark.asyncio
async def test_razorpay_webhook_idempotency_avoids_duplicate_onboarding():
    test_secret = "test_rzp_sec_xyz"
    razorpay_payment_provider.webhook_secret = test_secret

    uid = uuid.uuid4().hex[:6]
    test_domain = f"novaautorepair-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Nova Auto Repair",
            domain=test_domain,
            country="US",
            niche="Automotive",
            public_email=f"service@{test_domain}",
            pipeline_stage=PipelineStage.PROPOSAL.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        biz_id = biz.id

    webhook_payload = {
        "event": "payment_link.paid",
        "created_at": 1710001000,
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_nova_1122",
                    "amount": 60000,
                    "amount_paid": 60000,
                    "notes": {"business_id": str(biz_id)}
                }
            },
            "payment": {
                "entity": {
                    "id": f"pay_nova_dup_{uid}",
                    "amount": 60000,
                    "email": "service@novaautorepair.com"
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    valid_sig = hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First call: Processed
        res1 = await client.post(
            "/api/webhooks/razorpay",
            content=payload_bytes,
            headers={"X-Razorpay-Signature": valid_sig}
        )
        assert res1.status_code == 200
        assert res1.json()["status"] == "SUCCESS"

        # Duplicate call: Handled idempotently
        res2 = await client.post(
            "/api/webhooks/razorpay",
            content=payload_bytes,
            headers={"X-Razorpay-Signature": valid_sig}
        )
        assert res2.status_code == 200

    # Ensure only 1 payment and 1 customer created
    async with AsyncSessionLocal() as session:
        pmts = (await session.execute(
            select(Payment).where(Payment.reference_id == f"pay_nova_dup_{uid}")
        )).scalars().all()
        assert len(pmts) == 1

        custs = (await session.execute(
            select(Customer).where(Customer.business_id == biz_id)
        )).scalars().all()
        assert len(custs) == 1

def test_get_active_payment_provider_default_and_toggle():
    # By default, PAYMENT_PROVIDER is razorpay
    active = get_active_payment_provider()
    assert isinstance(active, RazorpayPaymentProvider)
