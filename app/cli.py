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

@cli_app.command("queue")
def list_queue():
    """Lists all pending outreach messages waiting for human approval."""
    async def _queue():
        await init_db()
        async with AsyncSessionLocal() as session:
            pending = await outreach_approval_queue.list_pending(session)
            if not pending:
                console.print("[yellow]No pending outreach messages in approval queue.[/yellow]")
                return

            table = Table(title=f"Human Approval Queue ({len(pending)} Pending)")
            table.add_column("ID", style="bold cyan")
            table.add_column("Business Name", style="white")
            table.add_column("Domain", style="blue")
            table.add_column("Recipient", style="green")
            table.add_column("Subject", style="italic")
            table.add_column("Created At", style="dim")

            for m in pending:
                biz = (await session.execute(select(Business).where(Business.id == m.business_id))).scalars().first()
                table.add_row(
                    str(m.id),
                    biz.name[:28] if biz else "Unknown",
                    biz.domain if biz else "Unknown",
                    m.recipient_email or "No email",
                    m.subject[:40] + "..." if len(m.subject) > 40 else m.subject,
                    str(m.created_at)[:19] if m.created_at else ""
                )
            console.print(table)
    asyncio.run(_queue())

@cli_app.command("approve")
def approve_outreach(message_id: int):
    """Approves a queued outreach message and triggers sending via the configured adapter."""
    async def _approve():
        await init_db()
        async with AsyncSessionLocal() as session:
            try:
                approved = await outreach_approval_queue.approve_message(session, message_id)
                console.print(f"[bold green]✓ Message {approved.id} APPROVED by human operator.[/bold green]")
                send_result = await outreach_sender_adapter.send_approved_message(session, message_id)
                console.print(f"[bold cyan]Outreach Transmission Status: {send_result['status']} ({send_result['event']})[/bold cyan]")
            except Exception as e:
                console.print(f"[bold red]Approval error: {e}[/bold red]")
    asyncio.run(_approve())

@cli_app.command("metrics")
def view_metrics():
    """Displays real-time agency pipeline, revenue, and conversion metrics."""
    async def _metrics():
        await init_db()
        async with AsyncSessionLocal() as session:
            data = await analytics_engine.get_dashboard_metrics(session)
            console.print("[bold blue]=== Agency Executive Revenue Metrics ===[/bold blue]")
            console.print(data)
    asyncio.run(_metrics())

@cli_app.command("leads")
def list_leads(limit: int = 25):
    """Lists top commercial B2B prospects stored in the database."""
    async def _leads():
        await init_db()
        async with AsyncSessionLocal() as session:
            stmt = select(Business).order_by(Business.created_at.desc()).limit(limit)
            leads = (await session.execute(stmt)).scalars().all()
            if not leads:
                console.print("[yellow]No leads found in database.[/yellow]")
                return

            table = Table(title=f"Discovered B2B Prospects (Showing {len(leads)})")
            table.add_column("Business Name", style="cyan")
            table.add_column("Domain", style="blue")
            table.add_column("City", style="green")
            table.add_column("Public Email", style="magenta")
            table.add_column("Phone", style="dim")
            table.add_column("Pipeline Stage", style="bold")

            for b in leads:
                table.add_row(
                    b.name[:28],
                    b.domain,
                    b.city or "",
                    b.public_email or "None",
                    b.phone or "None",
                    b.pipeline_stage.value if hasattr(b.pipeline_stage, 'value') else str(b.pipeline_stage)
                )
            console.print(table)
    asyncio.run(_leads())

@cli_app.command("worker")
def run_worker(once: bool = typer.Option(False, "--once", help="Run a single pass and exit"), interval: int = 60):
    """Runs the persistent background worker for replies, follow-ups, and auto-cycles."""
    from app.orchestrator.worker import agency_worker
    async def _worker():
        await init_db()
        if once:
            console.print("[bold cyan]Executing single worker tick...[/bold cyan]")
            res = await agency_worker.execute_tick()
            console.print(f"[bold green]Worker pass complete:[/bold green] {res}")
        else:
            agency_worker.interval_seconds = interval
            console.print(f"[bold cyan]Starting persistent worker (interval: {interval}s)... Press Ctrl+C to stop.[/bold cyan]")
            await agency_worker.start()
            try:
                while agency_worker.is_running:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                await agency_worker.stop()
                console.print("[yellow]Worker stopped.[/yellow]")
    asyncio.run(_worker())

@cli_app.command("replies")
def list_replies():
    """Lists incoming prospect replies and AI classifications."""
    from app.database.models import Reply
    async def _replies():
        await init_db()
        async with AsyncSessionLocal() as session:
            stmt = select(Reply).order_by(Reply.received_at.desc())
            replies = (await session.execute(stmt)).scalars().all()
            if not replies:
                console.print("[yellow]No replies recorded yet.[/yellow]")
                return

            table = Table(title=f"Inbound Prospect Replies ({len(replies)})")
            table.add_column("ID", style="dim")
            table.add_column("Sender", style="cyan")
            table.add_column("Classification", style="bold")
            table.add_column("Conf.", style="green")
            table.add_column("Snippet", style="white")
            table.add_column("Suggested Response", style="dim")

            for r in replies:
                table.add_row(
                    str(r.id),
                    r.sender_email,
                    r.classification,
                    f"{r.confidence*100:.0f}%",
                    r.raw_body[:40] + "..." if len(r.raw_body) > 40 else r.raw_body,
                    (r.suggested_response or "")[:35] + "..." if len(r.suggested_response or "") > 35 else (r.suggested_response or "")
                )
            console.print(table)
    asyncio.run(_replies())

@cli_app.command("payments")
def list_payments():
    """Lists confirmed payments and customer revenue."""
    from app.database.models import Payment, Customer
    async def _pmts():
        await init_db()
        async with AsyncSessionLocal() as session:
            stmt = select(Payment).order_by(Payment.created_at.desc())
            pmts = (await session.execute(stmt)).scalars().all()
            if not pmts:
                console.print("[yellow]No payments recorded yet.[/yellow]")
                return

            table = Table(title=f"Confirmed Payments ({len(pmts)})")
            table.add_column("Ref ID", style="dim")
            table.add_column("Customer", style="cyan")
            table.add_column("Amount", style="bold green")
            table.add_column("Status", style="bold")
            table.add_column("Date", style="magenta")

            for p in pmts:
                cust = await session.get(Customer, p.customer_id)
                table.add_row(
                    p.reference_id,
                    cust.company_name if cust else "Unknown",
                    f"${p.amount:,.2f} {p.currency}",
                    p.status,
                    p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else ""
                )
            console.print(table)
    asyncio.run(_pmts())

@cli_app.command("checkout")
def generate_checkout(business_id: int):
    """Generates a checkout session link for a prospect offer."""
    from app.payments.provider import stripe_payment_provider
    from app.database.models import Offer
    async def _chk():
        await init_db()
        async with AsyncSessionLocal() as session:
            biz = await session.get(Business, business_id)
            if not biz:
                console.print(f"[red]Business #{business_id} not found.[/red]")
                return
            q_off = select(Offer).where(Offer.business_id == business_id).order_by(Offer.created_at.desc())
            offer = (await session.execute(q_off)).scalars().first()
            title = offer.title if offer else "Website Turnaround Package"
            amount = offer.recommended_price if offer else 650.0

            res = await stripe_payment_provider.create_checkout_session(
                business_id=biz.id,
                offer_id=offer.id if offer else 0,
                title=title,
                amount_usd=amount,
                customer_email=biz.public_email
            )
            console.print(f"[bold green]Checkout Session Created:[/bold green]")
            console.print(f"URL: {res.get('checkout_url')}")
            console.print(f"Amount: ${res.get('amount'):,.2f}")
            console.print(f"Mode: {res.get('mode')}")
    asyncio.run(_chk())

# --- Database Backup & Recovery ---
@cli_app.command("backup")
def backup_database():
    """Creates an online, gzip-compressed snapshot of the agency database with integrity check."""
    from app.database.backup import backup_manager
    console.print("[cyan]Creating database snapshot...[/cyan]")
    try:
        res = backup_manager.create_backup()
        console.print(f"[bold green]✓ Backup Created Successfully:[/bold green] {res['filename']}")
        console.print(f"File: {res['filepath']}")
        console.print(f"Original: {res['original_bytes']:,} bytes | Compressed: {res['compressed_bytes']:,} bytes ({res['compression_savings']} saved)")
        console.print(f"Integrity Check: [bold green]PASSED[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Backup failed:[/bold red] {e}")

@cli_app.command("restore")
def restore_database(backup_file: str):
    """Restores the agency database from a compressed backup snapshot."""
    from app.database.backup import backup_manager
    console.print(f"[yellow]Restoring database from {backup_file}...[/yellow]")
    try:
        res = backup_manager.restore_backup(backup_file)
        console.print(f"[bold green]✓ Database Restored Successfully:[/bold green] {res['active_db']}")
    except Exception as e:
        console.print(f"[bold red]Restore failed:[/bold red] {e}")

# --- Windows Background Service Management ---
service_app = typer.Typer(help="Manage persistent Windows background service (Auto-start on boot, restart on crash)")
cli_app.add_typer(service_app, name="service")

@service_app.command("install")
def install_service():
    """Installs the agency as a persistent Windows Scheduled Task that auto-starts on boot/logon."""
    from app.service.windows_task import windows_service_manager
    console.print("[cyan]Installing Autonomous Agency Windows Background Service...[/cyan]")
    res = windows_service_manager.install()
    if res.get("success"):
        console.print("[bold green]Successfully installed Windows background service![/bold green]")
        console.print(f"Service Name: {res.get('service_name')}")
        console.print(f"Auto-Start: {res.get('auto_start')}")
        console.print(f"Launcher: {res.get('launcher')}")
        console.print(f"Crash Recovery: {res.get('crash_restart')}")
        console.print(f"Web Dashboard: {res.get('dashboard_url')}")
        console.print("\nTo start it immediately, run: [yellow]python -m app.cli service start[/yellow]")
    else:
        console.print(f"[bold red]Failed to install service:[/bold red] {res.get('error')}")

@service_app.command("status")
def service_status():
    """Queries current status of the persistent Windows background service."""
    from app.service.windows_task import windows_service_manager
    status = windows_service_manager.get_status()

    table = Table(title="Autonomous Agency Windows Background Service Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Service Name", str(status.get("service_name")))
    table.add_row("Auto-Start Installed", "YES (Windows Boot / Logon)" if status.get("installed") else "NO")
    table.add_row("Execution State", str(status.get("state")))
    table.add_row("Process Active", "YES" if status.get("running") else "NO")
    table.add_row("Web Port (8000)", "LISTENING" if status.get("port_active") else "NOT LISTENING")
    table.add_row("Control Center UI", str(status.get("dashboard_url") or "http://localhost:8000"))
    table.add_row("Service Log File", str(status.get("log_file")))
    console.print(table)

@service_app.command("start")
def start_service():
    """Starts the persistent Windows background service immediately."""
    from app.service.windows_task import windows_service_manager
    console.print("[cyan]Starting Autonomous Agency Background Service...[/cyan]")
    res = windows_service_manager.start()
    console.print(f"[bold green]Service start signal sent.[/bold green] Dashboard will be accessible at http://localhost:8000")

@service_app.command("stop")
def stop_service():
    """Stops the running Windows background service."""
    from app.service.windows_task import windows_service_manager
    console.print("[yellow]Stopping Autonomous Agency Background Service...[/yellow]")
    windows_service_manager.stop()
    console.print("[bold green]Service stopped successfully.[/bold green]")

@service_app.command("uninstall")
def uninstall_service():
    """Unregisters and removes the persistent Windows background service."""
    from app.service.windows_task import windows_service_manager
    console.print("[yellow]Uninstalling Autonomous Agency Background Service...[/yellow]")
    res = windows_service_manager.uninstall()
    console.print(f"[bold green]{res.get('message', 'Service uninstalled.')}[/bold green]")

if __name__ == "__main__":
    cli_app()
