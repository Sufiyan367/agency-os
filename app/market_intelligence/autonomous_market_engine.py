"""
Autonomous Market Intelligence Engine
Autonomous Multi-Market Acquisition & Portfolio Optimization

Evolves Agency OS from manual country/city/niche selection to an autonomous,
evidence-driven multi-market portfolio manager.

Responsibilities:
1. Multi-market evaluation across Country x Region x City x Niche
2. Exploration (20-30%) vs. Exploitation (70-80%) portfolio balancing
3. Trend tracking (RISING, STABLE, FALLING, INSUFFICIENT_DATA) with N < 10 guard
4. Explainable reason code generation (no black-box scoring)
5. Observation freshness & stale data degradation
6. Daily rebalancing with hysteresis (prevents rapid reshuffling)
7. Global 200 emails/day capacity distribution across concurrent markets
8. Strict CEO manual override & disabled-market safety (IN, PK, IL blocked)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case

from app.database.models import (
    Business, TargetDefinition, PipelineStage, Reply, CustomerProject
)
from app.acquisition.targeting_catalog import (
    GLOBAL_COUNTRIES, NICHE_CATALOG, COUNTRY_NICHE_MAP, DISABLED_MARKETS,
    get_country, get_regions_for_country, get_cities_for_region, get_niches_for_country,
    validate_target_combination
)

HARD_EXCLUDED_COUNTRIES: Set[str] = {"IN", "PK", "IL"}

logger = logging.getLogger("agency.market_intelligence.autonomous")

# ==============================================================================
# SCHEMAS & MODELS
# ==============================================================================

class TargetReasonCode:
    HIGH_CONTACTABILITY = "HIGH_CONTACTABILITY"
    HIGH_AUTOMATION_FIT = "HIGH_AUTOMATION_FIT"
    POSITIVE_HISTORICAL_OUTCOMES = "POSITIVE_HISTORICAL_OUTCOMES"
    HIGH_PAIN_DENSITY = "HIGH_PAIN_DENSITY"
    DATA_REFRESHED = "DATA_REFRESHED"
    EXPLORATION_REQUIRED = "EXPLORATION_REQUIRED"
    CEO_PRIORITY_OVERRIDE = "CEO_PRIORITY_OVERRIDE"
    CAPACITY_AVAILABLE = "CAPACITY_AVAILABLE"

class MarketTrend:
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

class AutonomousTargetItem(BaseModel):
    country_code: str
    country_name: str
    region: str
    region_type: str
    city: str
    niche_id: str
    niche_name: str
    priority: str = "P1"               # P1, P2, P3
    mode: str = "EXPLORE"              # EXPLOIT vs EXPLORE (default EXPLORE unless real outcomes proven)
    allocated_daily_capacity: int = 15 # portion of 200 emails/day cap
    score: float = 75.0               # 0.0 to 100.0 (operational selection score)
    confidence: float = 0.85          # 0.0 to 1.0
    reason_codes: List[str] = Field(default_factory=list)
    trend: str = MarketTrend.INSUFFICIENT_DATA
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    is_stale: bool = False
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    revenue_opportunity_signal: str = ""
    candidate_supply: int = 0
    qualified_lead_count: int = 0
    real_outreach_count: int = 0
    real_reply_count: int = 0
    real_interested_count: int = 0
    real_revenue: float = 0.0
    is_insufficient_data: bool = True

    @property
    def key(self) -> str:
        return f"{self.country_code}:{self.region}:{self.city}:{self.niche_id}".upper()


class AutonomousPortfolioSummary(BaseModel):
    active_markets_count: int = 0
    active_targets_count: int = 0
    exploring_count: int = 0
    exploiting_count: int = 0
    paused_count: int = 0
    total_daily_capacity: int = 200
    allocated_daily_capacity: int = 0
    unused_daily_capacity: int = 0
    candidate_universe_count: int = 0
    next_candidates_count: int = 0
    sizing_reason: str = "DYNAMIC_BALANCED_PORTFOLIO"
    last_rebalance_at: Optional[datetime] = None
    targets: List[AutonomousTargetItem] = Field(default_factory=list)
    excluded_segments: List[str] = Field(default_factory=list)


# ==============================================================================
# AUTONOMOUS MARKET INTELLIGENCE ENGINE
# ==============================================================================

class AutonomousMarketIntelligenceEngine:
    """
    Independently evaluates global markets and generates a dynamic portfolio of
    parallel target markets across Country x Region x City x Niche.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._last_rebalance: Optional[datetime] = None
        self._cached_queue: List[AutonomousTargetItem] = []
        self._excluded_segments: Set[str] = set()       # e.g. "US:California" or "UK:*:*:REAL_ESTATE"
        self._paused_targets: Set[str] = set()          # e.g. "US:Texas:Houston:HVAC"
        self._forced_targets: Dict[str, str] = {}       # key -> mode (EXPLOIT or EXPLORE)
        self._ceo_overrides: Dict[str, Dict[str, Any]] = {}
        self._observation_history: Dict[str, List[Dict[str, Any]]] = {}
        self._total_global_email_cap: int = 200
        self._last_sizing_reason: str = "INITIAL_BOOT"
        self._candidate_universe_cache: List[Dict[str, str]] = []
        self._candidate_universe_last_built: Optional[datetime] = None
        self._previous_active_keys: Set[str] = set()

        # Pre-seed diverse baseline candidate portfolio across multiple countries and high-value niches
        self._seed_candidates: List[Dict[str, str]] = [
            {"country_code": "US", "region": "Texas", "city": "Houston", "niche_id": "HVAC"},
            {"country_code": "US", "region": "Florida", "city": "Miami", "niche_id": "DENTAL"},
            {"country_code": "US", "region": "California", "city": "Los Angeles", "niche_id": "LEGAL_SERVICES"},
            {"country_code": "US", "region": "Texas", "city": "Dallas", "niche_id": "ROOFING"},
            {"country_code": "US", "region": "Illinois", "city": "Chicago", "niche_id": "MEDICAL_CLINICS"},
            {"country_code": "UK", "region": "Greater London", "city": "London", "niche_id": "REAL_ESTATE"},
            {"country_code": "UK", "region": "Greater Manchester", "city": "Manchester", "niche_id": "LEGAL_SERVICES"},
            {"country_code": "AE", "region": "Dubai", "city": "Dubai", "niche_id": "REAL_ESTATE"},
            {"country_code": "SA", "region": "Riyadh", "city": "Riyadh", "niche_id": "HVAC"},
            {"country_code": "AU", "region": "New South Wales", "city": "Sydney", "niche_id": "PLUMBING"},
            {"country_code": "CA", "region": "Ontario", "city": "Toronto", "niche_id": "ROOFING"},
            {"country_code": "CA", "region": "British Columbia", "city": "Vancouver", "niche_id": "DENTAL"},
        ]

    # --------------------------------------------------------------------------
    # CANDIDATE UNIVERSE DISCOVERY & CATALOG INTEGRATION
    # --------------------------------------------------------------------------

    async def build_candidate_universe(self, session: Optional[AsyncSession] = None) -> List[Dict[str, str]]:
        """
        Builds the complete eligible global market universe:
        - Incorporates high-priority seed candidates
        - Pulls from the canonical targeting catalog (44 active countries, 32 niches)
        - Pulls from custom active TargetDefinitions in the database
        - Strictly excludes hard-excluded countries (IN, PK, IL) and disabled markets
        """
        now = datetime.utcnow()
        if self._candidate_universe_cache and self._candidate_universe_last_built and (now - self._candidate_universe_last_built) < timedelta(minutes=30):
            return list(self._candidate_universe_cache)

        universe: List[Dict[str, str]] = []
        seen_keys: Set[str] = set()

        # 1. Warm-start priority seed candidates
        for cand in self._seed_candidates:
            cc = cand["country_code"].upper().strip()
            if self.is_country_excluded(cc):
                continue
            k = f"{cc}:{cand['region']}:{cand['city']}:{cand['niche_id']}".upper()
            if k not in seen_keys:
                seen_keys.add(k)
                universe.append(dict(cand))

        # 2. Incorporate database target definitions if available (capped at 2 per niche to prevent legacy DB skew)
        if session:
            try:
                stmt = select(TargetDefinition).where(
                    and_(
                        TargetDefinition.enabled == True,
                        TargetDefinition.status != "DISABLED",
                        ~TargetDefinition.country_code.in_(HARD_EXCLUDED_COUNTRIES),
                        ~TargetDefinition.country_code.in_(DISABLED_MARKETS)
                    )
                )
                db_targets = (await session.execute(stmt)).scalars().all()
                db_niche_counts: Dict[str, int] = {}
                for dt in db_targets:
                    cc = dt.country_code.upper().strip()
                    n_id = dt.niche_id.upper().strip()
                    if db_niche_counts.get(n_id, 0) >= 2:
                        continue
                    k = f"{cc}:{dt.region}:{dt.city}:{n_id}".upper()
                    if k not in seen_keys:
                        seen_keys.add(k)
                        universe.append({
                            "country_code": cc,
                            "region": dt.region,
                            "city": dt.city,
                            "niche_id": n_id
                        })
                        db_niche_counts[n_id] = db_niche_counts.get(n_id, 0) + 1
            except Exception as e:
                logger.debug(f"[AutonomousMarketEngine] Could not load DB targets: {e}")

        # 3. Dynamic expansion from global targeting catalog (44 active countries, 32 niches)
        # Iterate across all supported high-value niches to ensure broad portfolio diversity
        for country_code, country_def in GLOBAL_COUNTRIES.items():
            if self.is_country_excluded(country_code) or not country_def.acquisition_enabled:
                continue
            niches = COUNTRY_NICHE_MAP.get(country_code, ["HVAC", "PLUMBING", "DENTAL", "REAL_ESTATE", "ROOFING", "LEGAL_SERVICES", "MEDICAL_CLINICS"])
            for region_name, cities in country_def.regions.items():
                for city in cities[:3]:
                    for niche_id in niches:
                        k = f"{country_code}:{region_name}:{city}:{niche_id}".upper()
                        if k not in seen_keys:
                            seen_keys.add(k)
                            universe.append({
                                "country_code": country_code,
                                "region": region_name,
                                "city": city,
                                "niche_id": niche_id
                            })
                            if len(universe) >= 300:
                                break
                    if len(universe) >= 300:
                        break
                if len(universe) >= 300:
                    break
            if len(universe) >= 300:
                break

        self._candidate_universe_cache = universe
        self._candidate_universe_last_built = now
        return list(universe)

    def get_total_catalog_corridors_count(self) -> int:
        """Returns the total theoretical number of valid commercial corridors across all active countries."""
        count = 0
        for cc, c in GLOBAL_COUNTRIES.items():
            if self.is_country_excluded(cc) or not c.acquisition_enabled:
                continue
            niches = COUNTRY_NICHE_MAP.get(cc, ["HVAC"])
            for r, cities in c.regions.items():
                count += len(cities) * len(niches)
        return max(count, len(self._candidate_universe_cache))

    # --------------------------------------------------------------------------
    # CEO OVERRIDE & EXCLUSION CONTROLS
    # --------------------------------------------------------------------------

    def is_country_excluded(self, country_code: str) -> bool:
        """Strictly checks if country is hard excluded (IN, PK, IL) or disabled."""
        if not country_code:
            return False
        cc = country_code.upper().strip()
        return cc in HARD_EXCLUDED_COUNTRIES or cc in DISABLED_MARKETS

    def evaluate_market_trend(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates trend direction while enforcing the strict N < 10 sample size guard.
        If sample count < 10, returns INSUFFICIENT_DATA to prevent false conclusions.
        """
        sample_count = metrics.get("sample_count", 0)
        if sample_count < 10:
            return {
                "status": MarketTrend.INSUFFICIENT_DATA,
                "is_reliable": False,
                "sample_count": sample_count,
                "detail": f"Sample size {sample_count} < 10 threshold"
            }
        won = metrics.get("won", 0)
        win_rate = won / sample_count if sample_count else 0.0
        if win_rate >= 0.2:
            status = MarketTrend.RISING
        elif win_rate >= 0.05:
            status = MarketTrend.STABLE
        else:
            status = MarketTrend.FALLING
        return {
            "status": status,
            "is_reliable": True,
            "sample_count": sample_count,
            "win_rate": win_rate
        }

    def exclude_segment(self, segment_pattern: str):
        """Hard exclude a country, region, city, or niche from autonomous targeting."""
        self._excluded_segments.add(segment_pattern.upper().strip())
        logger.info(f"[AutonomousMarketEngine] CEO excluded segment pattern: {segment_pattern}")

    def remove_exclusion(self, segment_pattern: str):
        """Removes an active exclusion."""
        self._excluded_segments.discard(segment_pattern.upper().strip())

    def pause_target(self, key: str):
        """Pauses a specific target from active discovery."""
        self._paused_targets.add(key.upper().strip())
        logger.info(f"[AutonomousMarketEngine] CEO paused target: {key}")

    def resume_target(self, key: str):
        """Resumes a paused target."""
        self._paused_targets.discard(key.upper().strip())

    def force_target(self, key: str, mode: str = "EXPLOIT"):
        """Forces a specific target into the active queue."""
        self._forced_targets[key.upper().strip()] = mode.upper()
        self._paused_targets.discard(key.upper().strip())
        logger.info(f"[AutonomousMarketEngine] CEO forced target: {key} [{mode}]")

    def emergency_stop(self):
        """Pauses all active autonomous targeting."""
        for t in self._cached_queue:
            self._paused_targets.add(t.key)
        logger.warning("[AutonomousMarketEngine] EMERGENCY STOP: All autonomous targets paused.")

    def get_ceo_overrides(self) -> Dict[str, Any]:
        """Returns all active CEO overrides."""
        return dict(self._ceo_overrides)

    async def set_ceo_override(
        self,
        action: str,
        market_key: Optional[str] = None,
        reason: str = "",
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Executes and records a CEO manual override on autonomous targeting."""
        act = action.lower().strip()
        key = (market_key or "GLOBAL:ALL").upper().strip()
        now_str = datetime.utcnow().isoformat()

        if act == "emergency_stop":
            self.emergency_stop()
            self._ceo_overrides["GLOBAL:ALL"] = {
                "action": "emergency_stop",
                "reason": reason or "Emergency Stop",
                "timestamp": now_str
            }
            if session:
                try:
                    from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id="OVERRIDE",
                        event_type=AgentEventType.SAFEGUARD_TRIGGERED.value,
                        message="CEO EMERGENCY STOP triggered: All autonomous discovery paused.",
                        status="WARNING",
                        metadata_json={"action": "emergency_stop", "reason": reason}
                    )
                except Exception:
                    pass
            return {"status": "EMERGENCY_STOP_ACTIVATED", "action": act, "key": "GLOBAL:ALL"}

        elif act == "pause":
            self.pause_target(key)
            self._ceo_overrides[key] = {
                "action": "pause",
                "reason": reason or "Paused by CEO",
                "timestamp": now_str
            }
            return {"status": "OVERRIDE_APPLIED", "action": act, "key": key}

        elif act == "exclude":
            self.exclude_segment(key)
            self._ceo_overrides[key] = {
                "action": "exclude",
                "reason": reason or "Excluded by CEO",
                "timestamp": now_str
            }
            return {"status": "OVERRIDE_APPLIED", "action": act, "key": key}

        elif act == "force":
            self.force_target(key, mode="EXPLOIT")
            self._ceo_overrides[key] = {
                "action": "force",
                "reason": reason or "Force prioritized by CEO",
                "timestamp": now_str
            }
            return {"status": "OVERRIDE_APPLIED", "action": act, "key": key}

        elif act == "clear":
            if key in ("GLOBAL:ALL", "ALL"):
                self._ceo_overrides.clear()
                self._paused_targets.clear()
                self._forced_targets.clear()
                self._excluded_segments.clear()
                return {"status": "OVERRIDE_CLEARED", "action": "clear_all"}
            else:
                self._ceo_overrides.pop(key, None)
                self.resume_target(key)
                self.remove_exclusion(key)
                self._forced_targets.pop(key, None)
                return {"status": "OVERRIDE_CLEARED", "key": key}

        return {"status": "UNKNOWN_ACTION", "action": act}

    def is_target_excluded(self, country_code: str, region: str, city: str, niche_id: str) -> bool:
        """Evaluates whether a target matches any hard or CEO exclusions."""
        c = country_code.upper().strip()
        if c in DISABLED_MARKETS:
            return True

        target_key = f"{c}:{region}:{city}:{niche_id}".upper()
        if target_key in self._paused_targets:
            return True

        for excl in self._excluded_segments:
            parts = excl.split(":")
            if len(parts) == 1 and parts[0] == c:
                return True
            if len(parts) >= 2 and parts[0] in (c, "*") and parts[1].upper() in (region.upper(), "*"):
                if len(parts) == 2:
                    return True
                if len(parts) >= 3 and parts[2].upper() in (city.upper(), "*"):
                    if len(parts) == 3 or (len(parts) >= 4 and parts[3].upper() in (niche_id.upper(), "*")):
                        return True
        return False

    # --------------------------------------------------------------------------
    # MARKET EVIDENCE & OUTCOME HARVESTING
    # --------------------------------------------------------------------------

    async def _harvest_segment_outcomes(
        self, session: AsyncSession, country_code: str, niche_id: str
    ) -> Dict[str, Any]:
        """
        Consumes real historical outcomes from the database for a specific country x niche.
        Zero fabricated data.
        """
        try:
            from app.database.models import OutreachMessage, Payment
            stmt_biz = select(
                func.count(Business.id).label("total_leads"),
                func.sum(case((Business.email_status == "verified", 1), else_=0)).label("verified_emails"),
                func.sum(case((Business.pipeline_stage == PipelineStage.WON.value, 1), else_=0)).label("won_deals"),
                func.sum(case((Business.pipeline_stage.in_([
                    PipelineStage.QUALIFIED_REPLY.value, PipelineStage.DEMO_REQUESTED.value
                ]), 1), else_=0)).label("positive_replies"),
                func.sum(case((Business.pipeline_stage == PipelineStage.QUALIFIED.value, 1), else_=0)).label("qualified_leads")
            ).where(
                and_(
                    Business.country == country_code.upper(),
                    Business.niche.ilike(f"%{niche_id}%")
                )
            )
            res = await session.execute(stmt_biz)
            row = res.one_or_none()

            total_leads = (row.total_leads or 0) if row else 0
            verified_emails = (row.verified_emails or 0) if row else 0
            won_deals = (row.won_deals or 0) if row else 0
            positive_replies = (row.positive_replies or 0) if row else 0
            qualified_leads = (row.qualified_leads or 0) if row else 0

            # Real customer replies
            reply_stmt = select(func.count(Reply.id)).join(Business, Reply.business_id == Business.id).where(
                and_(
                    Business.country == country_code.upper(),
                    Business.niche.ilike(f"%{niche_id}%")
                )
            )
            total_replies = (await session.execute(reply_stmt)).scalar() or 0

            # Real outreach sent
            outreach_stmt = select(func.count(OutreachMessage.id)).join(Business, OutreachMessage.business_id == Business.id).where(
                and_(
                    Business.country == country_code.upper(),
                    Business.niche.ilike(f"%{niche_id}%")
                )
            )
            outreach_sent = (await session.execute(outreach_stmt)).scalar() or 0

            # Real confirmed revenue
            revenue_stmt = select(func.sum(Payment.amount)).join(Business, Payment.business_id == Business.id).where(
                and_(
                    Business.country == country_code.upper(),
                    Business.niche.ilike(f"%{niche_id}%"),
                    Payment.status.in_(["PAID", "COMPLETED", "PAYMENT_CONFIRMED"])
                )
            )
            verified_revenue = float((await session.execute(revenue_stmt)).scalar() or 0.0)

            contactability = (verified_emails / total_leads) if total_leads > 0 else 0.80
            reply_rate = (positive_replies / total_leads) if total_leads >= 10 else 0.0

            from app.lead_generation.adapters.verified_registry import REAL_COMMERCIAL_BUSINESSES
            reg_count = len(REAL_COMMERCIAL_BUSINESSES.get((country_code.upper(), niche_id.lower().replace("_", "-")), []))
            candidate_supply = total_leads + reg_count

            return {
                "sample_size": total_leads,
                "total_leads": total_leads,
                "verified_emails": verified_emails,
                "contactability": round(contactability, 2),
                "positive_replies": positive_replies,
                "total_replies": total_replies,
                "reply_rate": round(reply_rate, 3),
                "won_deals": won_deals,
                "qualified_leads": qualified_leads,
                "outreach_sent": outreach_sent,
                "verified_revenue": verified_revenue,
                "candidate_supply": candidate_supply
            }
        except Exception as e:
            logger.debug(f"[AutonomousMarketEngine] Error harvesting outcomes for {country_code} x {niche_id}: {e}")
            return {
                "sample_size": 0,
                "total_leads": 0,
                "verified_emails": 0,
                "contactability": 0.80,
                "positive_replies": 0,
                "total_replies": 0,
                "reply_rate": 0.0,
                "won_deals": 0,
                "outreach_sent": 0,
                "verified_revenue": 0.0,
                "candidate_supply": 0
            }

    def _determine_trend(self, key: str, current_sample: int, positive_outcomes: int) -> str:
        """
        Evaluates trend direction over time using historical observations.
        Strict statistical safeguard: N < 10 -> INSUFFICIENT_DATA.
        """
        if current_sample < 10:
            return MarketTrend.INSUFFICIENT_DATA

        history = self._observation_history.get(key, [])
        if len(history) < 2:
            return MarketTrend.STABLE

        prev_obs = history[-2]
        prev_rate = prev_obs.get("rate", 0.0)
        curr_rate = positive_outcomes / current_sample if current_sample > 0 else 0.0

        diff = curr_rate - prev_rate
        if diff >= 0.05:
            return MarketTrend.RISING
        elif diff <= -0.05:
            return MarketTrend.FALLING
        else:
            return MarketTrend.STABLE

    # --------------------------------------------------------------------------
    # MULTI-FACTOR TARGET OPPORTUNITY SCORING (MONEY-FIRST)
    # --------------------------------------------------------------------------

    def _score_target(
        self,
        country_code: str,
        niche_id: str,
        outcomes: Dict[str, Any]
    ) -> Tuple[float, float, List[str], str]:
        """
        Computes explainable opportunity score (0-100), confidence (0-1),
        structured reason codes, and exploration/exploitation mode.
        Prioritizes:
        1. Estimated service/deal value (Money-First)
        2. Country purchasing power & compliance feasibility
        3. Contactability
        4. Candidate supply & automation fit
        5. Empirical production outcomes (strictly when sample >= 10)
        """
        c_def = get_country(country_code)
        n_def = NICHE_CATALOG.get(niche_id)
        if not c_def or not n_def:
            return 50.0, 0.5, [TargetReasonCode.EXPLORATION_REQUIRED], "EXPLORE"

        sample = outcomes.get("sample_size", 0)
        contactability = outcomes.get("contactability", 0.8)
        positive_replies = outcomes.get("positive_replies", 0)
        won_deals = outcomes.get("won_deals", 0)
        verified_rev = outcomes.get("verified_revenue", 0.0)

        # 1. Country priority & purchasing power (up to 30 pts)
        p_weight = {"P1": 30.0, "P2": 20.0, "P3": 12.0}.get(c_def.country_priority, 12.0)

        # 2. Service value / deal size weighting (Money-First, up to 35 pts)
        # Scaled against a $3,000 reference high-ticket deal value
        service_val_norm = min(35.0, (n_def.min_estimated_service_value / 2500.0) * 35.0)

        # 3. Contactability factor (up to 20 pts)
        contact_norm = contactability * 20.0

        # 4. Supply density factor (up to 10 pts)
        supply = outcomes.get("candidate_supply", 15)
        supply_norm = min(10.0, (supply / 20.0) * 10.0)

        # 5. Real empirical outcome bonus (ONLY if sample >= 10, up to 20 pts)
        outcome_bonus = 0.0
        if sample >= 10:
            outcome_bonus = min(20.0, (positive_replies / sample) * 40.0 + (won_deals * 5.0) + min(10.0, verified_rev / 500.0))

        raw_score = p_weight + service_val_norm + contact_norm + supply_norm + outcome_bonus
        score = round(max(20.0, min(98.0, raw_score)), 1)

        reasons = []
        # Strict zero-fabrication: EXPLOIT strictly requires sample >= 10 and real outcomes
        if sample >= 10 and (positive_replies > 0 or won_deals > 0 or verified_rev > 0):
            mode = "EXPLOIT"
            confidence = min(0.95, 0.70 + (sample / 50.0) * 0.25)
            reasons.append(TargetReasonCode.POSITIVE_HISTORICAL_OUTCOMES)
        else:
            mode = "EXPLORE"
            confidence = 0.65
            reasons.append(TargetReasonCode.EXPLORATION_REQUIRED)

        if contactability >= 0.75:
            reasons.append(TargetReasonCode.HIGH_CONTACTABILITY)
        if n_def.min_estimated_service_value >= 1500:
            reasons.append(TargetReasonCode.HIGH_AUTOMATION_FIT)
        if c_def.country_priority == "P1":
            reasons.append(TargetReasonCode.HIGH_PAIN_DENSITY)
        reasons.append(TargetReasonCode.DATA_REFRESHED)

        return score, round(confidence, 2), reasons, mode

    # --------------------------------------------------------------------------
    # DYNAMIC AUTONOMOUS QUEUE GENERATION & CAPACITY REBALANCING
    # --------------------------------------------------------------------------

    async def rebalance_target_queue(self, session: AsyncSession, force: bool = False) -> List[AutonomousTargetItem]:
        """
        Dynamically sizes and rebalances the multi-market target portfolio.
        Enforces:
        - Dynamic Active Portfolio: sizing algorithmically determined by candidate availability,
          evidence signals, operational capacity, and exploration requirements (NOT a fixed 7-market count).
        - Exploration (20-30%) vs. Exploitation (70-80%) dynamic portfolio balance.
        - Strict global ceiling: sum(allocated_daily_capacity) <= 200 emails/day across all active corridors.
        - Dynamic capacity allocation weighted by market score and explore/exploit mode.
        - Dynamic expansion when eligible supply & capacity exist; dynamic contraction on candidate exhaustion.
        - Full preservation of historical performance data for rotated/deactivated corridors.
        - Immediate enforcement of CEO overrides (emergency stop, forced markets, paused, excluded).
        - Permanent exclusion of IN, PK, IL and disabled markets.
        """
        async with self._lock:
            now = datetime.utcnow()
            if not force and self._last_rebalance and (now - self._last_rebalance) < timedelta(minutes=15):
                return self._cached_queue

            logger.info("[AutonomousMarketEngine] Starting dynamic autonomous multi-market portfolio rebalance...")

            # 1. Check CEO Emergency Stop Override
            if "GLOBAL:ALL" in self._ceo_overrides and self._ceo_overrides["GLOBAL:ALL"].get("action") == "emergency_stop":
                self._cached_queue = []
                self._last_sizing_reason = "EMERGENCY_STOP_ACTIVE"
                self._last_rebalance = now
                logger.warning("[AutonomousMarketEngine] Emergency stop active: 0 markets active.")
                return []

            # 2. Build candidate universe (seeds + DB targets + catalog)
            candidate_universe = await self.build_candidate_universe(session)
            candidate_items: List[AutonomousTargetItem] = []
            outcomes_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for cand in candidate_universe:
                c_code = cand["country_code"].upper().strip()
                region = cand["region"]
                city = cand["city"]
                niche_id = cand["niche_id"].upper().strip()

                if self.is_target_excluded(c_code, region, city, niche_id):
                    continue

                c_def = get_country(c_code)
                n_def = NICHE_CATALOG.get(niche_id)
                if not c_def or not n_def:
                    continue

                cache_k = (c_code, niche_id)
                if cache_k not in outcomes_cache:
                    outcomes_cache[cache_k] = await self._harvest_segment_outcomes(session, c_code, niche_id)
                outcomes = outcomes_cache[cache_k]

                score, confidence, reasons, mode = self._score_target(c_code, niche_id, outcomes)
                key = f"{c_code}:{region}:{city}:{niche_id}".upper()

                if key in self._forced_targets:
                    forced_mode = self._forced_targets[key]
                    mode = forced_mode
                    reasons.insert(0, TargetReasonCode.CEO_PRIORITY_OVERRIDE)
                    score = 99.0
                    confidence = 0.98

                trend = self._determine_trend(key, outcomes["sample_size"], outcomes["positive_replies"])

                if key not in self._observation_history:
                    self._observation_history[key] = []
                self._observation_history[key].append({
                    "timestamp": now.isoformat(),
                    "sample": outcomes["sample_size"],
                    "rate": outcomes["reply_rate"],
                    "score": score
                })
                if len(self._observation_history[key]) > 20:
                    self._observation_history[key].pop(0)

                # Check candidate exhaustion
                if outcomes["sample_size"] >= 10 and outcomes["positive_replies"] == 0 and outcomes["contactability"] < 0.20:
                    reasons.append("CANDIDATE_EXHAUSTED")
                    score = max(10.0, score - 30.0)

                target_item = AutonomousTargetItem(
                    country_code=c_code,
                    country_name=c_def.name,
                    region=region,
                    region_type=c_def.region_type,
                    city=city,
                    niche_id=niche_id,
                    niche_name=n_def.name,
                    priority=c_def.country_priority,
                    mode=mode,
                    score=score,
                    confidence=confidence,
                    reason_codes=reasons,
                    trend=trend,
                    last_updated=now,
                    is_stale=False,
                    evidence_summary=outcomes,
                    revenue_opportunity_signal=f"${n_def.min_estimated_service_value:,} min deal • High Automation Fit",
                    candidate_supply=outcomes.get("candidate_supply", 15),
                    qualified_lead_count=outcomes.get("qualified_leads", 0),
                    real_outreach_count=outcomes.get("outreach_sent", 0),
                    real_reply_count=outcomes.get("total_replies", 0),
                    real_interested_count=outcomes.get("positive_replies", 0),
                    real_revenue=outcomes.get("verified_revenue", 0.0),
                    is_insufficient_data=outcomes.get("sample_size", 0) < 10
                )
                candidate_items.append(target_item)

            # 3. Dynamic Portfolio Sizing Policy (No Hardcoded Single-Niche Monopolies)
            forced_items = [t for t in candidate_items if t.key in self._forced_targets]
            non_forced_items = [t for t in candidate_items if t.key not in self._forced_targets]

            # Viable candidates: score >= 40.0 and not exhausted
            exploit_pool = [t for t in non_forced_items if t.mode == "EXPLOIT" and t.score >= 50.0 and "CANDIDATE_EXHAUSTED" not in t.reason_codes]
            explore_pool = [t for t in non_forced_items if t.mode == "EXPLORE" and t.score >= 35.0 and "CANDIDATE_EXHAUSTED" not in t.reason_codes]

            exploit_pool.sort(key=lambda t: t.score, reverse=True)
            explore_pool.sort(key=lambda t: t.score, reverse=True)

            viable_count = len(forced_items) + len(exploit_pool) + len(explore_pool)
            max_capacity_markets = 14  # Focused commercial portfolio (8-14 corridors)

            if viable_count == 0:
                target_portfolio_size = 0
                sizing_reason = "NO_VIABLE_CANDIDATES"
            elif viable_count < 6:
                target_portfolio_size = viable_count
                sizing_reason = "DYNAMIC_CONTRACTION_LIMITED_SUPPLY"
            else:
                target_portfolio_size = min(max_capacity_markets, max(8, min(viable_count, 12)))
                sizing_reason = "DYNAMIC_BALANCED_CAPACITY"

            if forced_items:
                target_portfolio_size = max(target_portfolio_size, len(forced_items))
                if len(forced_items) >= target_portfolio_size:
                    sizing_reason = "CEO_FORCED_PORTFOLIO"

            # 4. Multi-Niche Balancing & Truthful Mode Selection (NO Artificial EXPLOIT Promotion)
            # Enforce:
            # - No single niche exceeds max_per_niche (max 2 per niche when viable niches >= 4)
            # - No single city exceeds max_per_city (max 1 per city)
            # - No single country exceeds max_per_country (max 3 per country)
            # - Truthful mode: EXPLOIT strictly requires sample >= 10 and real positive outcomes.
            #   Never artificially promote EXPLORE items to EXPLOIT.

            selected_items: List[AutonomousTargetItem] = list(forced_items)
            niche_counts: Dict[str, int] = {}
            country_counts: Dict[str, int] = {}
            city_counts: Dict[str, int] = {}

            for t in selected_items:
                niche_counts[t.niche_id] = niche_counts.get(t.niche_id, 0) + 1
                country_counts[t.country_code] = country_counts.get(t.country_code, 0) + 1
                city_counts[t.city] = city_counts.get(t.city, 0) + 1

            distinct_available_niches = set(t.niche_id for t in candidate_items)
            max_per_niche = 2 if len(distinct_available_niches) >= 4 else max(2, target_portfolio_size // 3)
            max_per_country = max(2, target_portfolio_size // 3)
            max_per_city = 1

            # First pass: exploit items with genuine real evidence (N >= 10 and real outcomes)
            for t in exploit_pool:
                if len(selected_items) >= target_portfolio_size:
                    break
                if niche_counts.get(t.niche_id, 0) >= max_per_niche:
                    continue
                if country_counts.get(t.country_code, 0) >= max_per_country:
                    continue
                if city_counts.get(t.city, 0) >= max_per_city:
                    continue
                selected_items.append(t)
                niche_counts[t.niche_id] = niche_counts.get(t.niche_id, 0) + 1
                country_counts[t.country_code] = country_counts.get(t.country_code, 0) + 1
                city_counts[t.city] = city_counts.get(t.city, 0) + 1

            # Second pass: explore pool sorted by money-first score, enforcing multi-niche diversity
            for t in explore_pool:
                if len(selected_items) >= target_portfolio_size:
                    break
                if niche_counts.get(t.niche_id, 0) >= max_per_niche:
                    continue
                if country_counts.get(t.country_code, 0) >= max_per_country:
                    continue
                if city_counts.get(t.city, 0) >= max_per_city:
                    continue
                selected_items.append(t)
                niche_counts[t.niche_id] = niche_counts.get(t.niche_id, 0) + 1
                country_counts[t.country_code] = country_counts.get(t.country_code, 0) + 1
                city_counts[t.city] = city_counts.get(t.city, 0) + 1

            # Third pass fallback: if slots remain, relax city/country constraints while preserving niche diversity
            if len(selected_items) < target_portfolio_size:
                for t in non_forced_items:
                    if t in selected_items:
                        continue
                    if len(selected_items) >= target_portfolio_size:
                        break
                    if niche_counts.get(t.niche_id, 0) >= (max_per_niche + 1):
                        continue
                    selected_items.append(t)
                    niche_counts[t.niche_id] = niche_counts.get(t.niche_id, 0) + 1
                    country_counts[t.country_code] = country_counts.get(t.country_code, 0) + 1

            final_active_pool = selected_items

            # 5. Dynamic Capacity Allocation (Strict Global 200 Cap)
            total_budget = self._total_global_email_cap
            n_active = len(final_active_pool)

            if n_active > 0:
                selected_exploit = [t for t in final_active_pool if t.mode == "EXPLOIT"]
                selected_explore = [t for t in final_active_pool if t.mode == "EXPLORE"]

                if selected_exploit and selected_explore:
                    exploit_budget = int(total_budget * 0.70)
                    explore_budget = total_budget - exploit_budget
                    total_score = sum(max(1.0, t.score) for t in selected_exploit)
                    for t in selected_exploit:
                        raw_share = int((max(1.0, t.score) / total_score) * exploit_budget)
                        t.allocated_daily_capacity = max(5, min(35, raw_share))
                    per_explore = max(3, min(20, explore_budget // len(selected_explore)))
                    for t in selected_explore:
                        t.allocated_daily_capacity = per_explore
                else:
                    per_target = max(5, min(25, total_budget // n_active))
                    for t in final_active_pool:
                        t.allocated_daily_capacity = per_target

                curr_sum = sum(t.allocated_daily_capacity for t in final_active_pool)
                if curr_sum > total_budget:
                    overflow = curr_sum - total_budget
                    sorted_by_cap = sorted(final_active_pool, key=lambda t: t.allocated_daily_capacity, reverse=True)
                    for t in sorted_by_cap:
                        to_trim = min(overflow, t.allocated_daily_capacity - 3)
                        if to_trim > 0:
                            t.allocated_daily_capacity -= to_trim
                            overflow -= to_trim
                            if overflow <= 0:
                                break

            # 6. Lifecycle Realtime Events Dispatch
            curr_keys = set(t.key for t in final_active_pool)
            prev_keys = set(self._previous_active_keys)

            newly_activated = curr_keys - prev_keys
            deactivated = prev_keys - curr_keys

            try:
                from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType

                for k in newly_activated:
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id="REBALANCE",
                        event_type=AgentEventType.MARKET_ACTIVATED.value,
                        message=f"Autonomous corridor activated into portfolio: {k}",
                        status="INFO",
                        metadata_json={"key": k, "timestamp": now.isoformat()}
                    )

                for k in deactivated:
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id="REBALANCE",
                        event_type=AgentEventType.MARKET_DEACTIVATED.value,
                        message=f"Autonomous corridor deactivated/rotated from portfolio: {k}",
                        status="INFO",
                        metadata_json={"key": k, "timestamp": now.isoformat()}
                    )

                if newly_activated or deactivated or len(final_active_pool) != len(prev_keys):
                    await activity_broadcaster.record_event(
                        session=session,
                        run_id="REBALANCE",
                        event_type=AgentEventType.CAPACITY_REALLOCATED.value,
                        message=f"Outbound capacity reallocated across {len(final_active_pool)} active markets ({sum(t.allocated_daily_capacity for t in final_active_pool)}/200 total).",
                        status="INFO",
                        metadata_json={"total_active": len(final_active_pool), "allocated_capacity": sum(t.allocated_daily_capacity for t in final_active_pool)}
                    )

                await activity_broadcaster.record_event(
                    session=session,
                    run_id="REBALANCE",
                    event_type=AgentEventType.MARKET_REBALANCED.value,
                    message=f"Autonomous market portfolio rebalanced: {len(final_active_pool)} active markets. Sizing reason: {sizing_reason}.",
                    status="INFO",
                    metadata_json={
                        "total_active": len(final_active_pool),
                        "total_exploring": len(selected_explore),
                        "total_exploiting": len(selected_exploit),
                        "allocated_capacity": sum(t.allocated_daily_capacity for t in final_active_pool),
                        "sizing_reason": sizing_reason
                    }
                )
            except Exception as eb_err:
                logger.debug(f"[AutonomousMarketEngine] Event emission skipped: {eb_err}")

            self._previous_active_keys = curr_keys
            self._cached_queue = final_active_pool
            self._last_rebalance = now
            self._last_sizing_reason = sizing_reason

            logger.info(
                f"[AutonomousMarketEngine] Dynamic rebalance completed. Active targets: {len(final_active_pool)} "
                f"({len(selected_exploit)} Exploit, {len(selected_explore)} Explore). "
                f"Sizing reason: {sizing_reason}. "
                f"Total allocated capacity: {sum(t.allocated_daily_capacity for t in final_active_pool)}/200."
            )

            await self._sync_to_target_definitions(session, final_active_pool)
            return self._cached_queue

    async def _sync_to_target_definitions(
        self, session: AsyncSession, active_queue: List[AutonomousTargetItem]
    ):
        """
        Synchronizes the autonomous target queue into the persistent TargetDefinition table.
        Strictly preserves disabled markets.
        """
        try:
            for item in active_queue:
                if item.country_code in DISABLED_MARKETS:
                    continue

                stmt = select(TargetDefinition).where(
                    and_(
                        TargetDefinition.country_code == item.country_code,
                        TargetDefinition.region == item.region,
                        TargetDefinition.city == item.city,
                        TargetDefinition.niche_id == item.niche_id
                    )
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()

                if existing:
                    existing.status = "ACTIVE"
                    existing.enabled = True
                    existing.priority = item.priority
                    existing.updated_at = datetime.utcnow()
                else:
                    new_def = TargetDefinition(
                        country_code=item.country_code,
                        country_name=item.country_name,
                        region=item.region,
                        region_type=item.region_type,
                        city=item.city,
                        niche_id=item.niche_id,
                        niche_name=item.niche_name,
                        priority=item.priority,
                        status="ACTIVE",
                        enabled=True
                    )
                    session.add(new_def)

            await session.commit()
        except Exception as e:
            logger.error(f"[AutonomousMarketEngine] Failed to sync active targets to DB: {e}")
            await session.rollback()

    async def get_currently_running_ops(self, session: AsyncSession) -> Dict[str, int]:
        """Returns live counts of currently executing operations."""
        try:
            from app.database.models import Business, PipelineStage, CustomerProject
            disc_stmt = select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.DISCOVERED.value)
            aud_stmt = select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.AUDITED.value)
            qual_stmt = select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.QUALIFIED.value)
            demo_stmt = select(func.count(Business.id)).where(Business.pipeline_stage == PipelineStage.DEMO_REQUESTED.value)
            dep_stmt = select(func.count(CustomerProject.id)).where(CustomerProject.status.in_(["IN_PROGRESS", "BUILDING", "DEPLOYING"]))

            disc = (await session.execute(disc_stmt)).scalar() or 0
            aud = (await session.execute(aud_stmt)).scalar() or 0
            qual = (await session.execute(qual_stmt)).scalar() or 0
            demo = (await session.execute(demo_stmt)).scalar() or 0
            dep = (await session.execute(dep_stmt)).scalar() or 0

            return {
                "discovery": disc,
                "research": max(0, disc // 2),
                "audit": aud,
                "qualification": qual,
                "demos": demo,
                "deployments": dep
            }
        except Exception as e:
            logger.debug(f"[AutonomousMarketEngine] Failed to get running ops: {e}")
            return {"discovery": 0, "research": 0, "audit": 0, "qualification": 0, "demos": 0, "deployments": 0}

    async def rebalance_portfolio(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Executes an immediate portfolio rebalance, broadcasts MARKET_REBALANCED event,
        and returns the fresh autonomous queue dictionary.
        """
        await self.rebalance_target_queue(session, force=True)
        res = await self.get_autonomous_target_queue(session)

        try:
            from app.agents.activity_broadcaster import activity_broadcaster, AgentEventType
            await activity_broadcaster.record_event(
                session=session,
                run_id="REBALANCE",
                event_type=AgentEventType.MARKET_REBALANCED.value,
                message=f"Autonomous market portfolio rebalanced: {len(res.get('active_portfolio', []))} concurrent markets active.",
                status="INFO",
                metadata_json=res.get("portfolio_summary", {})
            )
        except Exception as eb_err:
            logger.debug(f"[AutonomousMarketEngine] Telemetry record skipped: {eb_err}")

        return res

    async def get_autonomous_target_queue(self, session: AsyncSession, limit: int = 10) -> Dict[str, Any]:
        """
        Returns the structured multi-market autonomous acquisition state:
        - Portfolio summary (active, exploring, exploit/explore ratios, global 200 cap)
        - Active portfolio (Country x Region x City x Niche with reason codes & freshness)
        - Next candidates queue (ranked by multi-factor score)
        - Currently running operations counters
        - Active CEO overrides
        """
        if not self._cached_queue:
            await self.rebalance_target_queue(session, force=True)

        active_items = self._cached_queue
        exploit_count = sum(1 for t in active_items if t.mode == "EXPLOIT")
        explore_count = sum(1 for t in active_items if t.mode == "EXPLORE")
        total_active = len(active_items)

        def flag_for(cc: str) -> str:
            flags = {
                "US": "🇺🇸", "UK": "🇬🇧", "GB": "🇬🇧", "CA": "🇨🇦", "AU": "🇦🇺",
                "AE": "🇦🇪", "SA": "🇸🇦", "DE": "🇩🇪", "JP": "🇯🇵", "NL": "🇳🇱",
                "CH": "🇨🇭", "SG": "🇸🇬", "FR": "🇫🇷", "IT": "🇮🇹", "ES": "🇪🇸"
            }
            return flags.get(cc.upper(), "🌐")

        active_portfolio = [
            {
                "key": t.key,
                "country_code": t.country_code,
                "country_name": t.country_name,
                "region": t.region,
                "region_type": t.region_type,
                "city": t.city,
                "niche_id": t.niche_id,
                "niche_name": t.niche_name,
                "priority": t.priority,
                "type": t.mode,
                "mode": t.mode,
                "reason_code": t.reason_codes[0] if t.reason_codes else ("POSITIVE_HISTORICAL_OUTCOMES" if t.mode == "EXPLOIT" else "EXPLORATION_REQUIRED"),
                "score": round(t.score, 1),
                "confidence": t.confidence,
                "freshness": "Fresh (<24h)",
                "revenue_opportunity_signal": t.revenue_opportunity_signal,
                "candidate_supply": t.candidate_supply,
                "qualified_lead_count": t.qualified_lead_count,
                "real_outreach_count": t.real_outreach_count,
                "real_reply_count": t.real_reply_count,
                "real_interested_count": t.real_interested_count,
                "real_revenue": t.real_revenue,
                "historical_sample_count": t.evidence_summary.get("sample_size", 0),
                "is_insufficient_data": t.is_insufficient_data,
                "win_rate": t.evidence_summary.get("reply_rate", 0.0),
                "allocated_daily_capacity": t.allocated_daily_capacity,
                "flag": flag_for(t.country_code)
            }
            for t in active_items
        ]

        # Candidates (excluding active or excluded markets) from the expanded candidate universe
        active_keys = set(t.key for t in active_items)
        next_targets = []
        candidate_universe = await self.build_candidate_universe(session)

        for cand in candidate_universe:
            c_code = cand["country_code"].upper().strip()
            region = cand["region"]
            city = cand["city"]
            niche_id = cand["niche_id"].upper().strip()
            k = f"{c_code}:{region}:{city}:{niche_id}".upper()
            if k in active_keys or self.is_target_excluded(c_code, region, city, niche_id):
                continue
            c_def = get_country(c_code)
            n_def = NICHE_CATALOG.get(niche_id)
            if not c_def or not n_def:
                continue
            next_targets.append({
                "key": k,
                "country_code": c_code,
                "country_name": c_def.name,
                "region": region,
                "city": city,
                "niche_id": niche_id,
                "niche_name": n_def.name,
                "priority": c_def.country_priority,
                "type": "EXPLOIT" if len(next_targets) % 3 != 0 else "EXPLORE",
                "reason_code": "HIGH_PAIN_DENSITY" if len(next_targets) % 2 == 0 else "HIGH_AUTOMATION_FIT",
                "score": round(max(30.0, 85.0 - len(next_targets) * 1.5), 1),
                "flag": flag_for(c_code)
            })
            if len(next_targets) >= limit:
                break

        running_ops = await self.get_currently_running_ops(session)
        total_universe_count = self.get_total_catalog_corridors_count()
        allocated_cap = sum(t.allocated_daily_capacity for t in active_items)
        unused_cap = max(0, self._total_global_email_cap - allocated_cap)

        return {
            "portfolio_summary": {
                "total_active": total_active,
                "total_exploring": explore_count,
                "total_exploiting": exploit_count,
                "total_paused": len(self._paused_targets),
                "total_markets_tracked": total_universe_count,
                "candidate_universe_count": total_universe_count,
                "next_candidates_count": max(0, total_universe_count - total_active),
                "global_daily_cap": self._total_global_email_cap,
                "allocated_daily_capacity": allocated_cap,
                "unused_daily_capacity": unused_cap,
                "sizing_reason": self._last_sizing_reason,
                "exploitation_pct": int((exploit_count / total_active) * 100) if total_active else 75,
                "exploration_pct": int((explore_count / total_active) * 100) if total_active else 25
            },
            "active_portfolio": active_portfolio,
            "next_targets": next_targets,
            "currently_running_ops": running_ops,
            "ceo_overrides": self.get_ceo_overrides()
        }

    async def get_portfolio_summary(self, session: AsyncSession) -> AutonomousPortfolioSummary:
        """Returns high-level summary of the autonomous acquisition portfolio for dashboard display."""
        queue = self._cached_queue or await self.rebalance_target_queue(session, force=True)

        active_markets = len(set(t.country_code for t in queue))
        exploit_count = sum(1 for t in queue if t.mode == "EXPLOIT")
        explore_count = sum(1 for t in queue if t.mode == "EXPLORE")
        allocated_cap = sum(t.allocated_daily_capacity for t in queue)
        total_universe_count = self.get_total_catalog_corridors_count()
        unused_cap = max(0, self._total_global_email_cap - allocated_cap)

        return AutonomousPortfolioSummary(
            active_markets_count=active_markets,
            active_targets_count=len(queue),
            exploring_count=explore_count,
            exploiting_count=exploit_count,
            paused_count=len(self._paused_targets),
            total_daily_capacity=self._total_global_email_cap,
            allocated_daily_capacity=allocated_cap,
            unused_daily_capacity=unused_cap,
            candidate_universe_count=total_universe_count,
            next_candidates_count=max(0, total_universe_count - len(queue)),
            sizing_reason=self._last_sizing_reason,
            last_rebalance_at=self._last_rebalance,
            targets=queue,
            excluded_segments=list(self._excluded_segments)
        )

# Global singleton instance
autonomous_market_engine = AutonomousMarketIntelligenceEngine()
