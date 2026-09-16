"""
Targeting Manager & Acquisition Queue Engine
Autonomous B2B Lead-Gen & Revenue Operations Platform

Manages:
- Database-backed TargetDefinition CRUD
- Strict Country -> Region -> City -> Niche hierarchy validation
- Priority queue generation (P1 > P2 > P3)
- Seed initialization of canonical commercial targets
- Real-time aggregation of targeting metrics for dashboard (zero fake metrics)
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete

from app.database.models import TargetDefinition
from app.acquisition.targeting_catalog import (
    validate_target_combination,
    GLOBAL_COUNTRIES,
    NICHE_CATALOG,
    COUNTRY_NICHE_MAP,
    normalize_niche_id,
    DISABLED_MARKETS
)
from app.core.logging import logger

DEFAULT_INITIAL_TARGETS = [
    {"country_code": "US", "region": "Texas", "city": "Houston", "niche_id": "HVAC", "priority": "P1"},
    {"country_code": "US", "region": "Florida", "city": "Miami", "niche_id": "DENTAL", "priority": "P1"},
    {"country_code": "AE", "region": "Dubai", "city": "Dubai", "niche_id": "REAL_ESTATE", "priority": "P1"},
    {"country_code": "SA", "region": "Eastern Province", "city": "Dammam", "niche_id": "HVAC", "priority": "P1"},
    {"country_code": "UK", "region": "Greater London", "city": "London", "niche_id": "REAL_ESTATE", "priority": "P1"},
    {"country_code": "CA", "region": "Ontario", "city": "Toronto", "niche_id": "DENTAL", "priority": "P1"},
]

class TargetingManager:
    """Manages acquisition targeting definitions, queueing, and hierarchy validation."""

    async def seed_default_targets_if_empty(self, session: AsyncSession) -> int:
        """Seeds initial default priority targets if the database table is currently empty."""
        # Enforce that any target in disabled markets is disabled immediately
        disable_stmt = (
            update(TargetDefinition)
            .where(TargetDefinition.country_code.in_(DISABLED_MARKETS))
            .values(status="DISABLED", enabled=False)
        )
        await session.execute(disable_stmt)
        await session.commit()

        count_stmt = select(func.count(TargetDefinition.id))
        res = await session.execute(count_stmt)
        count = res.scalar() or 0
        if count > 0:
            return 0

        seeded = 0
        for item in DEFAULT_INITIAL_TARGETS:
            try:
                validated = validate_target_combination(
                    country_code=item["country_code"],
                    region=item["region"],
                    city=item["city"],
                    niche_id=item["niche_id"]
                )
                target = TargetDefinition(
                    country_code=validated["country_code"],
                    country_name=validated["country_name"],
                    region=validated["region"],
                    region_type=validated["region_type"],
                    city=validated["city"],
                    niche_id=validated["niche_id"],
                    niche_name=validated["niche_name"],
                    priority=item.get("priority", "P1"),
                    enabled=True,
                    status="ACTIVE"
                )
                session.add(target)
                seeded += 1
            except Exception as e:
                logger.error(f"[TargetingManager] Failed to seed target {item}: {e}")

        if seeded > 0:
            await session.commit()
            logger.info(f"[TargetingManager] Seeded {seeded} initial canonical targeting definitions.")
        return seeded

    async def list_targets(
        self,
        session: AsyncSession,
        country_code: Optional[str] = None,
        region: Optional[str] = None,
        city: Optional[str] = None,
        niche_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[TargetDefinition]:
        """Queries configured targets with optional multi-attribute filters."""
        # Ensure default seed exists
        await self.seed_default_targets_if_empty(session)

        stmt = select(TargetDefinition)
        conditions = []

        if country_code:
            conditions.append(TargetDefinition.country_code == country_code.upper().strip())
        if region:
            conditions.append(TargetDefinition.region.ilike(f"%{region.strip()}%"))
        if city:
            conditions.append(TargetDefinition.city.ilike(f"%{city.strip()}%"))
        if niche_id:
            norm_niche = normalize_niche_id(niche_id) or niche_id.upper().strip()
            conditions.append(TargetDefinition.niche_id == norm_niche)
        if status:
            conditions.append(TargetDefinition.status == status.upper().strip())
        if priority:
            conditions.append(TargetDefinition.priority == priority.upper().strip())
        if enabled_only:
            conditions.append(TargetDefinition.enabled.is_(True))

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Order by priority (P1 > P2 > P3) then id
        stmt = stmt.order_by(TargetDefinition.priority.asc(), TargetDefinition.id.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def create_target(
        self,
        session: AsyncSession,
        country_code: str,
        region: str,
        city: str,
        niche: str,
        priority: str = "P1",
        status: str = "ACTIVE",
        enabled: bool = True
    ) -> TargetDefinition:
        """
        Validates hierarchy, verifies uniqueness, and creates a TargetDefinition.
        Raises ValueError if hierarchy is invalid or if a duplicate target exists.
        Strictly blocks target creation for disabled markets.
        """
        c_code_clean = country_code.upper().strip()
        if c_code_clean in DISABLED_MARKETS:
            raise ValueError(f"Market '{c_code_clean}' is DISABLED for acquisition. Targeting and outreach are strictly BLOCKED.")

        validated = validate_target_combination(
            country_code=country_code,
            region=region,
            city=city,
            niche_id=niche
        )

        c_code = validated["country_code"]
        v_region = validated["region"]
        v_city = validated["city"]
        v_niche_id = validated["niche_id"]

        # Duplicate check across (country_code, region, city, niche_id)
        dup_stmt = select(TargetDefinition).where(
            and_(
                TargetDefinition.country_code == c_code,
                TargetDefinition.region == v_region,
                TargetDefinition.city == v_city,
                TargetDefinition.niche_id == v_niche_id
            )
        )
        existing = (await session.execute(dup_stmt)).scalar_one_or_none()
        if existing:
            raise ValueError(
                f"Target already exists: {validated['country_name']} -> {v_region} -> {v_city} -> {validated['niche_name']} (ID: {existing.id})"
            )

        norm_priority = priority.upper().strip() if priority in ("P1", "P2", "P3") else "P1"
        norm_status = status.upper().strip() if status in ("ACTIVE", "PAUSED", "DISABLED") else "ACTIVE"

        target = TargetDefinition(
            country_code=c_code,
            country_name=validated["country_name"],
            region=v_region,
            region_type=validated["region_type"],
            city=v_city,
            niche_id=v_niche_id,
            niche_name=validated["niche_name"],
            priority=norm_priority,
            status=norm_status,
            enabled=enabled if norm_status == "ACTIVE" else False
        )
        session.add(target)
        await session.commit()
        await session.refresh(target)

        logger.info(f"[TargetingManager] Created target #{target.id}: {c_code}/{v_region}/{v_city}/{v_niche_id} [{norm_priority}]")
        return target

    async def update_target(
        self,
        session: AsyncSession,
        target_id: int,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> Optional[TargetDefinition]:
        """Updates status, priority, or enablement of an existing target."""
        stmt = select(TargetDefinition).where(TargetDefinition.id == target_id)
        target = (await session.execute(stmt)).scalar_one_or_none()
        if not target:
            return None

        if target.country_code in DISABLED_MARKETS:
            if (status and status.upper().strip() == "ACTIVE") or enabled is True:
                raise ValueError(f"Cannot enable or activate target: Market '{target.country_code}' is DISABLED for acquisition.")

        if priority and priority.upper().strip() in ("P1", "P2", "P3"):
            target.priority = priority.upper().strip()
        if status:
            new_status = status.upper().strip()
            if new_status in ("ACTIVE", "PAUSED", "DISABLED"):
                target.status = new_status
                if new_status == "ACTIVE":
                    target.enabled = True
                else:
                    target.enabled = False
        if enabled is not None:
            target.enabled = enabled
            if not enabled and target.status == "ACTIVE":
                target.status = "PAUSED"
            elif enabled and target.status != "ACTIVE":
                target.status = "ACTIVE"

        target.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(target)
        return target

    async def delete_target(self, session: AsyncSession, target_id: int) -> bool:
        """Removes a target definition."""
        stmt = select(TargetDefinition).where(TargetDefinition.id == target_id)
        target = (await session.execute(stmt)).scalar_one_or_none()
        if not target:
            return False
        await session.delete(target)
        await session.commit()
        return True

    async def get_active_target_queue(self, session: AsyncSession) -> List[TargetDefinition]:
        """
        Returns active targets sorted by Priority (P1 > P2 > P3) then creation order.
        Disabled and paused targets, as well as disabled markets, are strictly excluded.
        """
        await self.seed_default_targets_if_empty(session)
        stmt = select(TargetDefinition).where(
            and_(
                TargetDefinition.status == "ACTIVE",
                TargetDefinition.enabled.is_(True),
                TargetDefinition.country_code.not_in(DISABLED_MARKETS)
            )
        ).order_by(TargetDefinition.priority.asc(), TargetDefinition.id.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def get_targeting_summary(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Computes accurate summary metrics from the database and configuration.
        ZERO fabricated data.
        """
        await self.seed_default_targets_if_empty(session)

        # Query all targets
        all_targets_stmt = select(TargetDefinition)
        res = await session.execute(all_targets_stmt)
        targets = list(res.scalars().all())

        p1_markets = sum(1 for c in GLOBAL_COUNTRIES.values() if c.country_priority == "P1" and c.acquisition_enabled)
        p2_markets = sum(1 for c in GLOBAL_COUNTRIES.values() if c.country_priority == "P2" and c.acquisition_enabled)
        p3_markets = sum(1 for c in GLOBAL_COUNTRIES.values() if c.country_priority == "P3" and c.acquisition_enabled)
        disabled_markets = sum(1 for c in GLOBAL_COUNTRIES.values() if c.market_class == "DISABLED" or not c.acquisition_enabled or c.code in DISABLED_MARKETS)

        active_targets = [t for t in targets if t.status == "ACTIVE" and t.enabled and t.country_code not in DISABLED_MARKETS]
        p1_targets = [t for t in active_targets if t.priority == "P1"]
        p2_targets = [t for t in active_targets if t.priority == "P2"]
        p3_targets = [t for t in active_targets if t.priority == "P3"]

        active_regions = len(set((t.country_code, t.region) for t in active_targets))
        active_cities = len(set((t.country_code, t.city) for t in active_targets))
        active_niches = len(set(t.niche_id for t in active_targets))

        # Top active targets formatted for display
        sorted_active = sorted(active_targets, key=lambda t: (t.priority, t.id))
        top_list = [
            f"{t.country_code} / {t.region} / {t.city} / {t.niche_name} [{t.priority}]"
            for t in sorted_active[:5]
        ]

        return {
            "total_supported_countries": len(GLOBAL_COUNTRIES),
            "p1_markets_count": p1_markets,
            "p2_markets_count": p2_markets,
            "p3_markets_count": p3_markets,
            "disabled_markets_count": disabled_markets,
            "total_configured_targets": len(targets),
            "active_targets_count": len(active_targets),
            "p1_targets_count": len(p1_targets),
            "p2_targets_count": len(p2_targets),
            "p3_targets_count": len(p3_targets),
            "active_regions_count": active_regions,
            "active_cities_count": active_cities,
            "active_niches_count": active_niches,
            "top_active_targets": top_list
        }

    async def list_market_overview(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """
        Returns overview of all countries in the global catalog, their market class,
        priority tier, acquisition status, and active target count.
        """
        await self.seed_default_targets_if_empty(session)
        all_targets_stmt = select(TargetDefinition)
        res = await session.execute(all_targets_stmt)
        targets = list(res.scalars().all())

        # Map country_code -> count of active targets
        active_counts: Dict[str, int] = {}
        for t in targets:
            if t.status == "ACTIVE" and t.enabled and t.country_code not in DISABLED_MARKETS:
                active_counts[t.country_code] = active_counts.get(t.country_code, 0) + 1

        overview = []
        for code, c in GLOBAL_COUNTRIES.items():
            is_disabled = code in DISABLED_MARKETS or c.market_class == "DISABLED" or not c.acquisition_enabled
            status_str = "OFF" if is_disabled else ("ACTIVE" if active_counts.get(code, 0) > 0 else "IDLE")
            overview.append({
                "country_code": c.code,
                "country_name": c.name,
                "market_class": c.market_class,
                "priority": c.country_priority,
                "status": status_str,
                "acquisition_enabled": not is_disabled,
                "active_targets": 0 if is_disabled else active_counts.get(code, 0),
                "currency": c.currency,
                "region_type": c.region_type
            })

        priority_weight = {"P1": 1, "P2": 2, "P3": 3, "DISABLED": 4}
        return sorted(overview, key=lambda x: (priority_weight.get(x["priority"], 99), x["country_name"]))

targeting_manager = TargetingManager()
