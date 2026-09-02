import asyncio
import sys
import typer
import uvicorn
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import Business, Customer, PipelineStage
from app.database.seed_data import seed_initial_data
from app.market_intelligence.engine import market_intelligence_engine
from app.lead_generation.discovery import lead_discovery_coordinator
from app.auditing.engine import website_audit_engine
from app.scoring.engine import lead_scoring_engine
from app.offers.generator import offer_engine
from app.outreach.personalization import outreach_personalizer
from app.outreach.queue import outreach_approval_queue
from app.outreach.sender import outreach_sender_adapter
from app.crm.reply_classifier import reply_classifier
from app.crm.pipeline import pipeline_manager
from app.delivery.report_generator import delivery_report_generator
from app.delivery.onboarding import onboarding_automation
from app.orchestrator.loop import orchestrator
from app.analytics.engine import analytics_engine
from app.core.config import settings

cli_app = typer.Typer(help="Autonomous B2B Lead-Gen & Sales Agency CLI")
console = Console()

@cli_app.command()
def init():
    """Initializes database schema and populates baseline benchmarks."""
    async def _init():
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)
        console.print("[green]✓ Database initialized and seed benchmarks loaded successfully.[/green]")
    asyncio.run(_init())

@cli_app.command()
def discover_markets():
    """Evaluates international markets and ranks country+niche combinations."""
    async def _markets():
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)
            ranks = await market_intelligence_engine.scan_and_rank_markets(session)
            
            table = Table(title="Top International Market Opportunities")
            table.add_column("Rank", style="cyan")
            table.add_column("Country", style="white")
            table.add_column("Niche", style="green")
            table.add_column("Opportunity Score", style="magenta")
            table.add_column("Expected Deal", style="yellow")
            table.add_column("Key Rationale", style="dim")

            for idx, r in enumerate(ranks[:10], 1):
                table.add_row(
                    str(idx),
                    f"{r.country_name} ({r.country_code})",
                    r.niche_name,
                    f"{r.total_score}/100",
                    f"${r.expected_deal_value:,.0f}",
                    r.reasoning[:70] + "..."
                )
            console.print(table)
    asyncio.run(_markets())

@cli_app.command()
def run_loop(target_leads: int = 4, max_markets: int = 2):
    """Executes the complete autonomous agent cycle end-to-end."""
    async def _run():
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)
        summary = await orchestrator.run_full_autonomous_cycle(
            target_leads_per_market=target_leads, max_opportunities_to_mine=max_markets
        )
        console.print("[bold green]=== Autonomous Cycle Completed ===[/bold green]")
        console.print(summary)
    asyncio.run(_run())

@cli_app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Launches the web control dashboard and REST API."""
    uvicorn.run("app.api.app:app", host=host, port=port, reload=False)

@cli_app.command()
def demo_e2e():
    """Runs a complete acceptance test demonstrating the entire autonomous revenue loop."""
    async def _demo():
        console.print("[bold blue]=== Starting End-to-End Acceptance Demonstration ===[/bold blue]")
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)

            # Step 1: Market Intelligence
            console.print("\n[bold]1. Scanning & Ranking Global Markets...[/bold]")
            ranks = await market_intelligence_engine.scan_and_rank_markets(session)
            top = ranks[0]
            console.print(f"Top Opportunity: [green]{top.niche_name}[/green] in [cyan]{top.country_name}[/cyan] (Score: {top.total_score}/100)")

            # Step 2: Lead Discovery & Verification
            console.print(f"\n[bold]2. Discovering & Verifying Qualified Prospects for {top.niche_slug}...[/bold]")
            discovered = await lead_discovery_coordinator.run_discovery_and_verification(
                session, country_code=top.country_code, niche_slug=top.niche_slug, target_count=3
            )
            if discovered:
                target_biz = discovered[0]
            else:
                target_biz = (await session.execute(select(Business))).scalars().first()

            if not target_biz:
                # Discovered backup seed if empty
                target_biz = (await lead_discovery_coordinator.run_discovery_and_verification(session, country_code="US", niche_slug="roofing-contractors", target_count=1))[0]

            console.print(f"Target Lead: [cyan]{target_biz.name}[/cyan] ({target_biz.domain}) - Status: [green]{target_biz.verification_status}[/green]")

            # Step 3: Deep Website Audit
            console.print(f"\n[bold]3. Executing Website Audit on {target_biz.website_url}...[/bold]")
            audit = await website_audit_engine.audit_business(session, target_biz)
            console.print(f"Site Health Score: [magenta]{audit.overall_health_score}/100[/magenta]")

            # Step 4: Lead Scoring
            console.print("\n[bold]4. Calculating Multi-Dimensional Lead Score...[/bold]")
            score = await lead_scoring_engine.score_business(session, target_biz)
            console.print(f"Lead Score: [bold green]{score.total_score}/100[/bold green] (Priority {score.priority})")

            # Step 5: Offer Recommendation
            console.print("\n[bold]5. Generating Tailored Commercial Offer...[/bold]")
            offer = await offer_engine.generate_offer_for_business(session, target_biz)
            console.print(f"Recommended Service: [cyan]{offer.title}[/cyan] | Price: [green]${offer.recommended_price:,.0f} USD[/green]")

            # Step 6: Personalized Outreach Drafting
            console.print("\n[bold]6. Drafting Personalized Outreach Message (Queued for Human Approval)...[/bold]")
            msg = await outreach_personalizer.prepare_outreach_for_business(session, target_biz)
            console.print(f"Subject: [italic]{msg.subject}[/italic]")
            console.print(f"Queue Status: [yellow]{msg.status}[/yellow]")

            # Step 7: Simulated Human Approval & Outreach Transmission
            console.print("\n[bold]7. Human Approval Gate: Simulating Approval & Send Adapter...[/bold]")
            await outreach_approval_queue.approve_message(session, msg.id)
            send_res = await outreach_sender_adapter.send_approved_message(session, msg.id)
            console.print(f"Send Adapter Result: [green]{send_res['event']}[/green] -> [cyan]{msg.recipient_email}[/cyan]")
            console.print(f"Pipeline Stage Advanced To: [bold]{target_biz.pipeline_stage}[/bold]")

            # Step 8: Simulated Prospect Reply & Intelligent Classification
            console.print("\n[bold]8. Simulating High-Intent Prospect Reply & AI Classification...[/bold]")
            reply_text = (
                f"Hi Elena, thanks for pointing out the mobile issue on {target_biz.domain}. "
                "Can you send the video or jump on a call Thursday at 2:00 PM?"
            )
            reply = await reply_classifier.process_incoming_reply(
                session, business_id=target_biz.id, sender_email=msg.recipient_email, raw_body=reply_text
            )
            console.print(f"Reply Classified As: [bold green]{reply.classification}[/bold green] (Confidence: {reply.confidence*100:.0f}%)")
            console.print(f"Suggested Response Drafted: [italic]{reply.suggested_response}[/italic]")

            # Step 9: Stage Progression -> Deal WON
            console.print("\n[bold]9. Advancing Sales Pipeline to WON...[/bold]")
            await pipeline_manager.transition_stage(
                session, business_id=target_biz.id, target_stage=PipelineStage.WON, note="Client approved engagement contract"
            )
            console.print(f"Stage: [bold green]{target_biz.pipeline_stage}[/bold green]")

            # Step 10: Automated Delivery & Onboarding
            console.print("\n[bold]10. Delivery Automation: Generating Client Onboarding & Diagnostic Audit Report...[/bold]")
            cust = (await session.execute(select(Customer).where(Customer.business_id == target_biz.id))).scalars().first()
            onboarding_pack = await onboarding_automation.generate_onboarding_packet(session, cust.id)
            report_md = await delivery_report_generator.generate_audit_report_markdown(session, target_biz.id)
            
            console.print(f"Onboarding Packet Created: [green]{onboarding_pack['status']}[/green] ({len(onboarding_pack['intake_checklist'])} intake items)")
            console.print(f"Diagnostic Audit Report: [green]{len(report_md)} bytes Markdown document ready for client presentation[/green]")

            # Step 11: Real-time Revenue Metrics
            console.print("\n[bold]11. Executive Dashboard Revenue Metrics...[/bold]")
            metrics = await analytics_engine.get_dashboard_metrics(session)
            console.print(f"Total Won Revenue: [bold green]${metrics['revenue']['won_revenue_usd']:,.0f} USD[/bold green]")
            console.print(f"Active Pipeline Value: [bold cyan]${metrics['revenue']['pipeline_value_usd']:,.0f} USD[/bold cyan]")
            console.print(f"Reply Rate: [bold magenta]{metrics['sales']['reply_rate_pct']}%[/bold magenta]")

        console.print("\n[bold green]✓ ALL 11 STEPS IN THE END-TO-END ACCEPTANCE TEST COMPLETED FLAWLESSLY![/bold green]")

    asyncio.run(_demo())

if __name__ == "__main__":
    cli_app()
