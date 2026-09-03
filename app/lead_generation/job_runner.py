# ==============================================================================
# Autonomous Prospecting Job Runner & Lifecycle Manager
# ==============================================================================
import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from app.core.logging import logger
from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import SystemRun
from app.lead_generation.targeting import (
    load_targeting_config, TargetingConfig, CommercialConfig, TargetingFilters
)
from app.lead_generation.providers.prospect_provider import (
    RealProspectProvider, MockProspectProvider
)
from app.lead_generation.service import LeadDiscoveryService


class ProspectingJobManager:
    """
    Canonical background job manager for autonomous prospecting cycles triggered
    from the Dashboard or developer scripts.
    Guarantees that both Dashboard and CLI use the same underlying service layer.
    """

    def __init__(self):
        self._current_job: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()
        self._active_task: Optional[asyncio.Task] = None

    def get_current_status(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns the current or most recent prospecting job status and live progress."""
        if not self._current_job:
            return {
                "job_id": None,
                "status": "IDLE",
                "started_at": None,
                "completed_at": None,
                "progress": {
                    "markets_being_searched": [],
                    "current_city_niche": "",
                    "prospects_discovered": 0,
                    "duplicates_rejected": 0,
                    "junk_rejected": 0,
                    "prospects_passing_500": 0,
                    "prospects_saved": 0,
                    "message": "Prospecting engine is idle. Ready to start."
                },
                "targeting": {},
                "summary": None,
                "error_message": None
            }

        if job_id and self._current_job.get("job_id") != job_id:
            # If specific job_id asked but doesn't match current, return current anyway
            pass

        return dict(self._current_job)

    async def start_prospecting_job(
        self,
        targeting_params: Dict[str, Any],
        provider_type: str = "real"
    ) -> Dict[str, Any]:
        """
        Validates parameters and starts an asynchronous prospecting cycle.
        Rejects if a job is currently RUNNING or QUEUED.
        """
        async with self._lock:
            if self._current_job and self._current_job.get("status") in ("QUEUED", "RUNNING"):
                # Check if task is actually still alive
                if self._active_task and not self._active_task.done():
                    return {
                        "job_id": self._current_job["job_id"],
                        "status": self._current_job["status"],
                        "already_running": True,
                        "message": "A prospecting cycle is already in progress."
                    }

            # Enforce Commercial Floor: must be >= $500
            min_service_value = float(targeting_params.get("min_service_value", 500.0))
            if min_service_value < 500.0:
                raise ValueError(
                    f"Minimum commercial value (${min_service_value:.2f}) cannot be less than the $500.00 floor."
                )

            max_prospects = int(targeting_params.get("max_prospects", 20))
            if max_prospects < 1:
                max_prospects = 20

            # Build TargetingConfig from baseline config and overrides
            base_config = load_targeting_config()

            countries = targeting_params.get("countries")
            cities = targeting_params.get("cities")
            niches = targeting_params.get("niches")

            if countries:
                base_config.target_countries = [c.upper().strip() for c in countries if c.strip()]
                base_config.country_code = base_config.target_countries[0] if base_config.target_countries else "US"
            else:
                base_config.target_countries = [base_config.country_code]

            if cities:
                base_config.cities = [c.strip() for c in cities if c.strip()]
            if niches:
                base_config.niches = [n.strip() for n in niches if n.strip()]

            base_config.commercial.minimum_target_service_value_usd = int(min_service_value)
            base_config.commercial.max_prospects_per_cycle = max_prospects
            base_config.filters.target_results_per_city = max_prospects

            job_id = f"proc_{uuid.uuid4().hex[:8]}"
            markets_list = [
                f"{c} - {ct}" for c in base_config.target_countries for ct in base_config.cities
            ]

            self._current_job = {
                "job_id": job_id,
                "status": "QUEUED",
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "progress": {
                    "markets_being_searched": markets_list,
                    "current_city_niche": f"{base_config.cities[0]} / {base_config.niches[0]}" if base_config.cities and base_config.niches else "",
                    "prospects_discovered": 0,
                    "duplicates_rejected": 0,
                    "junk_rejected": 0,
                    "prospects_passing_500": 0,
                    "prospects_saved": 0,
                    "message": "Job queued. Initializing real prospect provider..."
                },
                "targeting": {
                    "countries": base_config.target_countries,
                    "cities": base_config.cities,
                    "niches": base_config.niches,
                    "min_service_value": base_config.commercial.minimum_target_service_value_usd,
                    "max_prospects": base_config.commercial.max_prospects_per_cycle
                },
                "summary": None,
                "error_message": None
            }

            # Launch background task
            self._active_task = asyncio.create_task(
                self._execute_job(job_id, base_config, provider_type)
            )

            logger.info(f"Started prospecting cycle job '{job_id}' (Targeting: {base_config.target_countries}, {base_config.cities})")
            return {
                "job_id": job_id,
                "status": "QUEUED",
                "message": "Autonomous prospecting cycle successfully queued."
            }

    async def _execute_job(self, job_id: str, targeting: TargetingConfig, provider_type: str):
        """Asynchronously executes the prospecting cycle using the canonical LeadDiscoveryService."""
        start_time = datetime.utcnow()
        try:
            self._current_job["status"] = "RUNNING"
            self._current_job["progress"]["message"] = "Connecting to verified registries and discovery providers..."

            if provider_type.lower() == "mock":
                provider = MockProspectProvider()
            else:
                provider = RealProspectProvider()

            service = LeadDiscoveryService(provider=provider)

            async def handle_progress(data: Dict[str, Any]):
                if self._current_job and self._current_job.get("job_id") == job_id:
                    p = self._current_job["progress"]
                    if "markets_being_searched" in data:
                        p["markets_being_searched"] = data["markets_being_searched"]
                    if "market" in data and "niche" in data:
                        p["current_city_niche"] = f"{data['market']} / {data['niche']}"
                    if "prospects_discovered" in data:
                        p["prospects_discovered"] = data["prospects_discovered"]
                    if "duplicates_rejected" in data:
                        p["duplicates_rejected"] = data["duplicates_rejected"]
                    if "junk_rejected" in data:
                        p["junk_rejected"] = data["junk_rejected"]
                    if "prospects_passing_500" in data:
                        p["prospects_passing_500"] = data["prospects_passing_500"]
                    if "prospects_saved" in data:
                        p["prospects_saved"] = data["prospects_saved"]
                    if "message" in data:
                        p["message"] = data["message"]

            async with AsyncSessionLocal() as session:
                valid_prospects, stats = await service.discover_and_process(
                    targeting=targeting,
                    db=session,
                    check_existing_db=True,
                    progress_callback=handle_progress
                )

                # Record SystemRun
                duration = (datetime.utcnow() - start_time).total_seconds()
                system_run = SystemRun(
                    run_id=job_id,
                    job_name="autonomous_prospecting_cycle",
                    status="COMPLETED",
                    records_processed=stats.businesses_discovered,
                    records_failed=stats.duplicates_removed + stats.invalid_rejected,
                    duration_seconds=duration,
                    started_at=start_time,
                    finished_at=datetime.utcnow()
                )
                session.add(system_run)
                await session.commit()

            # Mark Completed
            self._current_job["status"] = "COMPLETED"
            self._current_job["completed_at"] = datetime.utcnow().isoformat()
            self._current_job["progress"]["prospects_saved"] = stats.valid_businesses
            self._current_job["progress"]["message"] = (
                f"Prospecting completed: {stats.valid_businesses} validated prospects ($500+ minimum) saved to pipeline."
            )
            self._current_job["summary"] = {
                "businesses_discovered": stats.businesses_discovered,
                "valid_businesses": stats.valid_businesses,
                "duplicates_removed": stats.duplicates_removed,
                "invalid_rejected": stats.invalid_rejected,
                "priority_prospects": stats.priority_prospects,
                "five_hundred_plus_prospects": stats.five_hundred_plus_prospects,
                "duration_seconds": round(duration, 1)
            }
            logger.info(f"Prospecting job '{job_id}' completed successfully: {stats.valid_businesses} prospects saved.")

        except Exception as e:
            logger.error(f"Prospecting job '{job_id}' failed: {e}", exc_info=True)
            if self._current_job and self._current_job.get("job_id") == job_id:
                self._current_job["status"] = "FAILED"
                self._current_job["completed_at"] = datetime.utcnow().isoformat()
                self._current_job["error_message"] = str(e)
                self._current_job["progress"]["message"] = f"Prospecting cycle failed: {str(e)}"

                try:
                    async with AsyncSessionLocal() as session:
                        duration = (datetime.utcnow() - start_time).total_seconds()
                        system_run = SystemRun(
                            run_id=job_id,
                            job_name="autonomous_prospecting_cycle",
                            status="FAILED",
                            records_processed=0,
                            records_failed=1,
                            duration_seconds=duration,
                            error_log=str(e),
                            started_at=start_time,
                            finished_at=datetime.utcnow()
                        )
                        session.add(system_run)
                        await session.commit()
                except Exception as log_err:
                    logger.debug(f"Failed to record system run error: {log_err}")


prospecting_job_manager = ProspectingJobManager()
