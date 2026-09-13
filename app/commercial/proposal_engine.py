"""Proposal Engine & Commercial Agreement Generator.

Transforms validated project specifications and deterministic pricing into formal,
customer-facing proposals and legal agreements.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import html
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    CustomerProject, Business, ProjectProposal, ProjectEvent,
    CommercialProposalStatus, ProjectStatus, ProjectSpecification
)
from app.commercial.pricing_engine import PricingEngine, PricingBreakdown
from app.core.config import settings
from app.core.logging import logger


class ProposalEngine:
    """Generates immutable, versioned commercial proposals."""

    @classmethod
    async def generate_proposal(
        cls,
        session: AsyncSession,
        project_id: int,
        selected_addons: Optional[List[str]] = None,
        custom_notes: Optional[str] = None,
        timeline_days: int = 5
    ) -> ProjectProposal:
        project = await session.get(CustomerProject, project_id)
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        biz = await session.get(Business, project.business_id)
        if not biz:
            raise ValueError(f"Business #{project.business_id} not found.")

        # Latest spec version
        latest_spec_ver = 1
        spec_stmt = select(ProjectSpecification).where(
            ProjectSpecification.project_id == project.id
        ).order_by(ProjectSpecification.version.desc())
        latest_spec = (await session.execute(spec_stmt)).scalars().first()
        if latest_spec:
            latest_spec_ver = latest_spec.version

        # Compute deterministic pricing
        pricing = PricingEngine.calculate_pricing(
            industry=project.industry,
            selected_addons=selected_addons
        )

        # Next proposal version for this project
        stmt = select(ProjectProposal).where(ProjectProposal.project_id == project.id)
        existing = (await session.execute(stmt)).scalars().all()
        prop_ver = len(existing) + 1

        proposal_id_str = f"PROP-{project.customer_slug.upper()}-{prop_ver:02d}"

        # Standard deliverables
        deliverables = [
            {
                "phase": "PHASE_1_PROTOTYPE_VALIDATION",
                "title": "Interactive Client Prototype & Sandbox Review",
                "details": f"Turnkey tailored interactive prototype demonstrating missed-call recovery and intake triage for {biz.name}."
            },
            {
                "phase": "PHASE_2_PRODUCTION_ENGINEERING",
                "title": "Production Application Deployment & AI Tuning",
                "details": "High-performance responsive frontend, domain-guarded conversational AI agent, and secure routing integration."
            },
            {
                "phase": "PHASE_3_QA_VERIFICATION",
                "title": "Automated 20-Gate Quality & Security Verification",
                "details": "Deterministic syntax verification, route accessibility, secret scanning, and CSP security compliance."
            },
            {
                "phase": "PHASE_4_HANDOVER",
                "title": "Verified Production Staging Handover & Training",
                "details": "Live deployment verification, operator credential handover, rollback documentation, and support channel activation."
            }
        ]

        assumptions = [
            "Client provides brand assets (logo, preferred brand colors) or accepts Stitch design tokens.",
            "Client designates a technical or operational contact for staging review and credential handover.",
            "Handover balance (60%) is due strictly upon verified staging completion."
        ]

        exclusions = [
            "Third-party SMS/telephony carrier usage fees beyond standard initial testing volume.",
            "Ongoing custom software feature development beyond the agreed specification scope.",
            "Client-side legacy infrastructure refactoring."
        ]

        warranty = (
            "30-Day Defect Warranty: Any functional discrepancy from the approved technical specification "
            "will be remediated at zero additional cost within 30 days of production handover."
        )

        acceptance_terms = (
            "Authorization of this proposal locks the canonical technical specification and authorizes mobilization. "
            "Production delivery requires verified payment of the 40% milestone deposit."
        )

        proposal = ProjectProposal(
            project_id=project.id,
            business_id=biz.id,
            proposal_id=proposal_id_str,
            version=prop_ver,
            specification_version=latest_spec_ver,
            status=CommercialProposalStatus.PROPOSAL_GENERATED.value,
            scope_summary=f"Turnkey AI Customer Intake & Lead Conversion System for {biz.name}",
            deliverables=deliverables,
            timeline_days=timeline_days,
            base_price_usd=pricing.base_price_usd,
            complexity_addon_usd=pricing.total_addons_usd,
            total_price_usd=pricing.total_price_usd,
            advance_deposit_usd=pricing.advance_deposit_usd,
            balance_due_usd=pricing.balance_due_usd,
            payment_terms={
                "milestones": pricing.payment_milestones,
                "commercial_floor_usd": getattr(settings, "COMMERCIAL_FLOOR_USD", 500.0),
                "currency": "USD"
            },
            assumptions=assumptions,
            exclusions=exclusions,
            warranty_terms=warranty,
            acceptance_terms=acceptance_terms,
            expires_at=datetime.utcnow() + timedelta(days=14),
            created_at=datetime.utcnow()
        )

        session.add(proposal)
        await session.flush()

        event = ProjectEvent(
            project_id=project.id,
            event_type="PROPOSAL_GENERATED",
            stage="PROPOSAL",
            details={
                "proposal_id": proposal.proposal_id,
                "version": proposal.version,
                "total_price_usd": proposal.total_price_usd,
                "advance_deposit_usd": proposal.advance_deposit_usd
            },
            created_at=datetime.utcnow()
        )
        session.add(event)
        await session.commit()
        await session.refresh(proposal)

        logger.info(f"[ProposalEngine] Generated proposal {proposal.proposal_id} for project #{project.id} (${proposal.total_price_usd:,.2f}).")
        return proposal

    @classmethod
    def render_proposal_html(cls, proposal: ProjectProposal, business: Business) -> str:
        """Generates a clean, customer-safe responsive HTML web proposal."""
        biz_name = html.escape(business.name or "Valued Client")
        prop_id = html.escape(proposal.proposal_id)
        total_price = f"${proposal.total_price_usd:,.2f}"
        deposit = f"${proposal.advance_deposit_usd:,.2f}"
        balance = f"${proposal.balance_due_usd:,.2f}"

        deliverables_html = "".join([
            f"""
            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:14px 16px; margin-bottom:10px;">
                <div style="font-size:0.7rem; color:#38bdf8; font-weight:700; text-transform:uppercase; letter-spacing:0.05em;">{html.escape(d.get('phase', ''))}</div>
                <div style="font-size:0.95rem; font-weight:600; color:#ffffff; margin:4px 0;">{html.escape(d.get('title', ''))}</div>
                <div style="font-size:0.8rem; color:#94a3b8; line-height:1.4;">{html.escape(d.get('details', ''))}</div>
            </div>
            """
            for d in (proposal.deliverables or [])
        ])

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Commercial Proposal — {biz_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #09090b;
            color: #f4f4f5;
            font-family: 'Inter', -apple-system, sans-serif;
            line-height: 1.5;
            padding: 24px 16px;
        }}
        .container {{
            max-width: 840px;
            margin: 0 auto;
            background: #121214;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 12px 40px rgba(0,0,0,0.6);
        }}
        .header {{
            padding: 28px 32px;
            background: linear-gradient(180deg, rgba(56,189,248,0.08) 0%, rgba(18,18,20,0) 100%);
            border-bottom: 1px solid rgba(255,255,255,0.08);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .body-section {{
            padding: 28px 32px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .pill {{
            background: rgba(56,189,248,0.12);
            color: #38bdf8;
            border: 1px solid rgba(56,189,248,0.3);
            border-radius: 20px;
            padding: 4px 12px;
            font-size: 0.72rem;
            font-weight: 600;
            display: inline-block;
        }}
        .pricing-card {{
            background: #09090b;
            border: 1px solid rgba(16,185,129,0.3);
            border-radius: 10px;
            padding: 20px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin: 16px 0;
        }}
        .btn-auth {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: #ffffff;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            width: 100%;
            transition: opacity 0.15s ease;
        }}
        .btn-auth:hover {{ opacity: 0.92; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <span class="pill">COMMERCIAL PROPOSAL</span>
                <h1 style="font-size:1.5rem; font-weight:700; color:#ffffff; margin-top:8px;">{biz_name}</h1>
                <p style="color:#94a3b8; font-size:0.85rem;">{html.escape(proposal.scope_summary)}</p>
            </div>
            <div style="text-align:right;">
                <div style="font-size:0.75rem; color:#71717a;">Proposal Ref</div>
                <div style="font-size:1.1rem; font-weight:700; color:#38bdf8; font-family:monospace;">{prop_id}</div>
                <div style="font-size:0.75rem; color:#71717a; margin-top:4px;">Turnaround: {proposal.timeline_days} Business Days</div>
            </div>
        </div>

        <div class="body-section">
            <h2 style="font-size:1.1rem; font-weight:700; color:#ffffff; margin-bottom:14px;">Scope of Deliverables</h2>
            {deliverables_html}
        </div>

        <div class="body-section">
            <h2 style="font-size:1.1rem; font-weight:700; color:#ffffff; margin-bottom:10px;">Transparent Milestone Pricing</h2>
            <div class="pricing-card">
                <div>
                    <span style="font-size:0.75rem; color:#71717a; text-transform:uppercase;">Total Fixed Turnkey</span>
                    <div style="font-size:1.5rem; font-weight:700; color:#ffffff; margin-top:4px;">{total_price}</div>
                </div>
                <div>
                    <span style="font-size:0.75rem; color:#34d399; text-transform:uppercase;">40% Milestone Advance</span>
                    <div style="font-size:1.5rem; font-weight:700; color:#34d399; margin-top:4px;">{deposit}</div>
                    <div style="font-size:0.7rem; color:#71717a;">Due upon authorization</div>
                </div>
                <div>
                    <span style="font-size:0.75rem; color:#71717a; text-transform:uppercase;">60% Handover Balance</span>
                    <div style="font-size:1.5rem; font-weight:700; color:#f4f4f5; margin-top:4px;">{balance}</div>
                    <div style="font-size:0.7rem; color:#71717a;">Due strictly upon verified handover</div>
                </div>
            </div>
            <p style="font-size:0.78rem; color:#94a3b8;">
                Commercial Guarantee: Zero hidden fees. Milestone balance is payable only after live production staging verification and operator QA sign-off.
            </p>
        </div>

        <div class="body-section" style="background:#09090b;">
            <h3 style="font-size:0.9rem; font-weight:700; color:#ffffff; margin-bottom:8px;">Acceptance & Authorization</h3>
            <p style="font-size:0.78rem; color:#94a3b8; margin-bottom:16px;">
                {html.escape(proposal.acceptance_terms)}
            </p>
            <form action="/api/proposals/{proposal.id}/accept" method="POST" id="auth-form">
                <button type="submit" class="btn-auth">
                    Authorize Proposal &amp; Request Payment Instructions ({deposit})
                </button>
            </form>
        </div>
    </div>
</body>
</html>
"""
