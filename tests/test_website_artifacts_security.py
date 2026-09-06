import pytest
import os
import uuid
from httpx import AsyncClient, ASGITransport

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import Business, Artifact, VerificationStatus, PipelineStage
from app.delivery.website_builder import WebsiteBuilder, ARTIFACTS_ROOT
from app.api.app import app
from app.core.config import settings


@pytest.mark.asyncio
async def test_website_artifact_generation_and_security_containment():
    """
    PHASE 7: Website Artifact Security & Containment Test.
    Verifies:
      1. Safe disk writing within ARTIFACTS_ROOT.
      2. Metadata persistence.
      3. Preview endpoint functionality.
      4. Path traversal attempts (e.g. '../etc/passwd') are strictly blocked with 400/403/404.
      5. Frame-ancestors & X-Frame-Options headers are enforced.
      6. No secrets or API keys are leaked into rendered HTML.
    """
    await init_db()
    uid = uuid.uuid4().hex[:6]
    domain = f"artifact-sec-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Artifact Sec Co {uid}",
            domain=domain,
            website_url=f"https://{domain}",
            country="US",
            city="Austin",
            niche="Commercial Roofing",
            public_email=f"info@{domain}",
            phone="+15125550199",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.AUDITED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        biz_id = biz.id

        # 1. Generate website artifact
        artifact = await WebsiteBuilder.build_website_for_business(
            session=session,
            business=biz,
            audit_results={"performance_score": 45.0, "load_time_seconds": 4.2},
            offer_proposal={"title": "High Performance Web Overhaul", "price": 950.0}
        )
        assert artifact is not None
        assert artifact.id is not None
        art_id = artifact.id
        rel_path = artifact.path

    # 2. Verify artifact is saved strictly inside ARTIFACTS_ROOT
    disk_path = os.path.abspath(os.path.join(ARTIFACTS_ROOT, rel_path))
    assert os.path.exists(disk_path)
    assert os.path.commonpath([disk_path, ARTIFACTS_ROOT]) == ARTIFACTS_ROOT

    # 3. Verify Preview Endpoint via HTTP
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. Valid Preview Request
        resp = await client.get(f"/api/artifacts/{art_id}/preview")
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" in resp.text
        assert domain in resp.text

        # B. Verify Security Headers (iframe containment)
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in resp.headers.get("Content-Security-Policy", "")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

        # C. Secret Leakage Verification: Ensure no configured secrets appear in HTML
        assert settings.DASHBOARD_PASSWORD not in resp.text
        assert settings.API_SECRET_KEY not in resp.text
        assert settings.SESSION_SECRET not in resp.text

        # D. Path Traversal Defense: Manipulate artifact path in DB to attempt traversal
        async with AsyncSessionLocal() as session:
            mal_artifact = Artifact(
                business_id=biz_id,
                artifact_type="WEBSITE",
                name="Malicious Traversal Artifact",
                path="../../etc/passwd",
                preview_url="/api/artifacts/traversal/preview"
            )
            session.add(mal_artifact)
            await session.commit()
            await session.refresh(mal_artifact)
            mal_id = mal_artifact.id

        mal_resp = await client.get(f"/api/artifacts/{mal_id}/preview")
        assert mal_resp.status_code in (400, 403, 404)
        assert "passwd" not in mal_resp.text
