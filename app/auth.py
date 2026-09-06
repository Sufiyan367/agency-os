import asyncio
import sys
import typer
from rich.console import Console

from app.core.auth_service import auth_service
from app.database.connection import AsyncSessionLocal, init_db

app = typer.Typer(help="Autonomous Agency Administrator Authentication CLI")
console = Console()

@app.callback()
def main_callback():
    """Autonomous Agency Administrator Authentication & Security CLI."""
    pass

@app.command("reset-admin")
def reset_admin(
    force: bool = typer.Option(False, "--force", "-y", help="Bypass confirmation prompt")
):
    """
    Clears the administrator account credentials from the database.
    Forces the dashboard to show the first-launch setup screen on next launch.
    """
    from app.core.config import settings
    if getattr(settings, "APP_ENV", "development").lower() == "production":
        console.print("[bold red]Refusing to reset admin in production environment.[/bold red]")
        raise typer.Exit(code=1)

    if not force:
        confirmed = typer.confirm("This will clear administrator credentials and require setup on next launch. Continue?")
        if not confirmed:
            console.print("[yellow]Aborted. Admin credentials untouched.[/yellow]")
            raise typer.Abort()

    async def _reset():
        await init_db()
        async with AsyncSessionLocal() as session:
            success = await auth_service.reset_admin_user(session)
            if success:
                console.print("[bold green]✓ Admin credentials reset successfully. First-launch setup will trigger on next launch.[/bold green]")
            else:
                console.print("[yellow]No admin credentials found to reset. Setup is already required.[/yellow]")

    asyncio.run(_reset())

if __name__ == "__main__":
    app()
