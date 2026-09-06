import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import Business, VerificationStatus, PipelineStage
from app.delivery.website_builder import WebsiteBuilder
import uuid

def test_caddyfile_upstream_variable_and_defaults():
    """1. Verifies that both root Caddyfile and deploy/Caddyfile use dynamic UPSTREAM_HOST."""
    for caddy_path in ["Caddyfile", "deploy/Caddyfile"]:
        assert os.path.exists(caddy_path), f"{caddy_path} must exist"
        with open(caddy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "{$UPSTREAM_HOST:127.0.0.1}:8000" in content, (
            f"{caddy_path} must use dynamic upstream '{{$UPSTREAM_HOST:127.0.0.1}}:8000'"
        )
        # Ensure hardcoded 127.0.0.1:8000 without the variable does not exist
        lines = [line.strip() for line in content.splitlines()]
        for line in lines:
            if line.startswith("reverse_proxy") and "127.0.0.1:8000" in line:
                assert "{$UPSTREAM_HOST:127.0.0.1}:8000" in line, (
                    f"Found hardcoded reverse_proxy target without variable in {caddy_path}: {line}"
                )

def test_caddyfile_websocket_proxy_configuration():
    """2. Verifies WebSocket proxy matcher and upstream configuration in Caddyfiles."""
    for caddy_path in ["Caddyfile", "deploy/Caddyfile"]:
        with open(caddy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "@websockets" in content
        assert "Upgrade websocket" in content or "Upgrade    websocket" in content
        assert "reverse_proxy @websockets {$UPSTREAM_HOST:127.0.0.1}:8000" in content

def test_caddyfile_route_specific_csp_and_frame_ancestors():
    """3. Verifies CSP frame-ancestors and X-Frame-Options fallback without overwriting upstream."""
    for caddy_path in ["Caddyfile", "deploy/Caddyfile"]:
        with open(caddy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "?X-Frame-Options" in content
        assert "?Content-Security-Policy" in content
        assert "frame-ancestors 'none'" in content

def test_caddyfile_production_security_headers_present():
    """4. Verifies presence of HSTS, MIME sniffing, referrer, and permissions policies."""
    for caddy_path in ["Caddyfile", "deploy/Caddyfile"]:
        with open(caddy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Strict-Transport-Security" in content
        assert "nosniff" in content
        assert "Referrer-Policy" in content
        assert "Permissions-Policy" in content
        assert "-Server" in content

def test_production_compose_caddy_and_upstream_wiring():
    """5. Verifies deploy/docker-compose.prod.yml service names and UPSTREAM_HOST."""
    compose_path = "deploy/docker-compose.prod.yml"
    assert os.path.exists(compose_path)
    with open(compose_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Service name must be agency-app
    assert "agency-app:" in content
    assert "container_name: agency-app" in content

    # Caddy service must have UPSTREAM_HOST=agency-app
    assert "agency-caddy" in content
    assert "UPSTREAM_HOST=agency-app" in content

    # FastAPI must NOT be exposed on 0.0.0.0:8000
    assert "0.0.0.0:8000" not in content
    assert "expose:" in content and "8000" in content

    # Caddy depends on agency-app healthy
    assert "condition: service_healthy" in content

@pytest.mark.asyncio
async def test_fastapi_preview_endpoint_frame_ancestors_and_sameorigin():
    """6. Verifies FastAPI preview endpoint sets X-Frame-Options: SAMEORIGIN and frame-ancestors 'self'."""
    await init_db()
    uid = uuid.uuid4().hex[:6]
    domain = f"caddy-csp-{uid}.com"

    async with AsyncSessionLocal() as session:
        biz = Business(
            name=f"Caddy CSP Co {uid}",
            domain=domain,
            website_url=f"https://{domain}",
            country="US",
            city="Austin",
            niche="HVAC Services",
            public_email=f"contact@{domain}",
            phone="+15125550188",
            verification_status=VerificationStatus.VERIFIED.value,
            pipeline_stage=PipelineStage.AUDITED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        artifact = await WebsiteBuilder.build_website_for_business(
            session=session,
            business=biz,
            audit_results={"performance_score": 50.0, "load_time_seconds": 3.8},
            offer_proposal={"title": "High Converting Landing Page", "price": 1200.0}
        )
        art_id = artifact.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/artifacts/{art_id}/preview")
        assert resp.status_code == 200
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in resp.headers.get("Content-Security-Policy", "")
