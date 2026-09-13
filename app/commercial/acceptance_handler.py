"""Customer Acceptance & Change Feedback Loop Handler.

Coordinates client demo review outcomes:
- CUSTOMER_ACCEPTED: Generates formal proposal and advances sales state machine.
- CUSTOMER_REQUESTED_CHANGES: Creates version-incremented canonical specification (v2, v3)
  without mutating prior versions, then triggers automated rebuild.
- CUSTOMER_DECLINED: Records decision and reasons cleanly.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    CustomerProject, Business, CustomerAcceptance, ProjectProposal,
    ProjectSpecification, ProjectEvent, CustomerAcceptanceStatus,
    CommercialProposalStatus, ProjectStatus, PipelineStage
)
from app.builder.spec_engine import CanonicalSpecEngine
from app.commercial.proposal_engine import ProposalEngine
from app.core.logging import logger


class AcceptanceHandler:
    """Orchestrates demo acceptance and change request iteration."""

    @classmethod
    async def accept_demo(
        cls,
        session: AsyncSession,
        project_id: int,
        feedback_notes: str = "Demo meets customer requirements.",
        actor: str = "CLIENT"
    ) -> Dict[str, Any]:
        project = await session.get(CustomerProject, project_id)
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        biz = await session.get(Business, project.business_id)
        if not biz:
            raise ValueError(f"Business #{project.business_id} not found.")

        # Create acceptance record
        acceptance = CustomerAcceptance(
            project_id=project.id,
            decision=CustomerAcceptanceStatus.ACCEPTED.value,
            status=CustomerAcceptanceStatus.ACCEPTED.value,
            feedback_notes=feedback_notes,
            change_requests=[],
            actor=actor,
            created_at=datetime.utcnow()
        )
        session.add(acceptance)

        # Update Project stage
        project.current_stage = "ACCEPTED"
        project.status = ProjectStatus.READY.value
        if biz:
            biz.pipeline_stage = PipelineStage.PROPOSAL.value

        # Generate commercial proposal
        proposal = await ProposalEngine.generate_proposal(
            session=session,
            project_id=project.id,
            custom_notes=feedback_notes
        )

        event = ProjectEvent(
            project_id=project.id,
            event_type="DEMO_ACCEPTED",
            stage="PROPOSAL",
            details={
                "actor": actor,
                "notes": feedback_notes,
                "proposal_id": proposal.proposal_id
            },
            created_at=datetime.utcnow()
        )
        session.add(event)
        await session.commit()
        await session.refresh(project)

        logger.info(f"[AcceptanceHandler] Project #{project.id} demo ACCEPTED by {actor}. Generated proposal {proposal.proposal_id}.")
        return {
            "project_id": project.id,
            "status": CustomerAcceptanceStatus.ACCEPTED.value,
            "decision": CustomerAcceptanceStatus.ACCEPTED.value,
            "acceptance_id": acceptance.id,
            "proposal_id": proposal.id,
            "proposal_ref": proposal.proposal_id,
            "total_price_usd": proposal.total_price_usd,
            "advance_deposit_usd": proposal.advance_deposit_usd,
            "proposal": {
                "id": proposal.id,
                "proposal_id": proposal.proposal_id,
                "total_price_usd": proposal.total_price_usd,
                "advance_deposit_usd": proposal.advance_deposit_usd,
                "balance_due_usd": proposal.balance_due_usd,
                "status": proposal.status,
                "deliverables": proposal.deliverables
            }
        }

    @classmethod
    async def request_changes(
        cls,
        session: AsyncSession,
        project_id: int,
        change_requests: List[Dict[str, Any]],
        feedback_notes: str = "",
        actor: str = "CLIENT"
    ) -> Dict[str, Any]:
        """Creates version-incremented specification (e.g. v2) and triggers rebuild."""
        project = await session.get(CustomerProject, project_id)
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        biz = await session.get(Business, project.business_id)
        if not biz:
            raise ValueError(f"Business #{project.business_id} not found.")

        # Record acceptance entity with change requests
        acceptance = CustomerAcceptance(
            project_id=project.id,
            decision=CustomerAcceptanceStatus.CHANGES_REQUESTED.value,
            status=CustomerAcceptanceStatus.CHANGES_REQUESTED.value,
            feedback_notes=feedback_notes,
            change_requests=change_requests,
            actor=actor,
            created_at=datetime.utcnow()
        )
        session.add(acceptance)

        # Get latest spec to branch from
        stmt = select(ProjectSpecification).where(
            ProjectSpecification.project_id == project.id
        ).order_by(ProjectSpecification.version.desc())
        latest_spec = (await session.execute(stmt)).scalars().first()

        next_version = (latest_spec.version + 1) if latest_spec else 2

        # Combine existing customer requests with new change requests
        existing_requests = list(latest_spec.customer_requests or []) if latest_spec else []
        new_items = []
        for i, chg in enumerate(change_requests):
            req_text = chg.get("requested_change") or chg.get("description", "")
            new_items.append({
                "request_id": f"REQ-CHG-{next_version}-{i+1}",
                "request": req_text,
                "description": req_text,
                "category": chg.get("category", "FEATURE_MODIFICATION"),
                "priority": chg.get("priority", "HIGH"),
                "source": "CLIENT_FEEDBACK"
            })
        combined_requests = existing_requests + new_items

        # Synthesize new immutable spec version with change requests
        change_text = " ".join([chg.get("requested_change") or chg.get("description", "") for chg in change_requests])
        spec_record = await CanonicalSpecEngine.build_canonical_spec(
            session=session,
            customer_project=project,
            reply_text=f"{feedback_notes} {change_text}".strip()
        )

        # Mark all prior specs as not canonical, and preserve combined requests
        stmt_all = select(ProjectSpecification).where(
            ProjectSpecification.project_id == project.id,
            ProjectSpecification.id != spec_record.id
        )
        prev_specs = (await session.execute(stmt_all)).scalars().all()
        for s in prev_specs:
            s.is_canonical = False

        spec_record.customer_requests = combined_requests
        spec_record.is_canonical = True

        project.current_stage = "BUILDING"
        project.status = ProjectStatus.BUILDING.value

        event = ProjectEvent(
            project_id=project.id,
            event_type="SPEC_VERSION_INCREMENTED",
            stage="BUILDING",
            details={
                "previous_version": latest_spec.version if latest_spec else 1,
                "new_version": spec_record.version,
                "change_count": len(change_requests)
            },
            created_at=datetime.utcnow()
        )
        session.add(event)
        await session.commit()
        await session.refresh(project)

        logger.info(f"[AcceptanceHandler] Project #{project.id} changes requested. Spec incremented to v{spec_record.version}.")
        return {
            "project_id": project.id,
            "status": CustomerAcceptanceStatus.CHANGES_REQUESTED.value,
            "decision": CustomerAcceptanceStatus.CHANGES_REQUESTED.value,
            "acceptance_id": acceptance.id,
            "new_spec_version": spec_record.version,
            "new_specification_version": spec_record.version,
            "spec_checksum": spec_record.checksum
        }
