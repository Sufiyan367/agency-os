"""Phase 10: Global Multi-Country Prospect Acquisition and Sequential Outreach Engine."""

from app.acquisition.models import (
    StandardizedProspect,
    CountryConfigDTO,
    ActiveSlotStatus,
    GlobalQueueItem,
)
from app.acquisition.config import country_config_manager
from app.acquisition.pipeline import CountryPipeline
from app.acquisition.pool import global_prospect_pool, GlobalProspectPool
from app.acquisition.ranking import global_ranker, GlobalRanker
from app.acquisition.controller import active_prospect_controller, ActiveProspectController
from app.acquisition.providers.registry import discovery_registry

__all__ = [
    "StandardizedProspect",
    "CountryConfigDTO",
    "ActiveSlotStatus",
    "GlobalQueueItem",
    "country_config_manager",
    "CountryPipeline",
    "global_prospect_pool",
    "GlobalProspectPool",
    "global_ranker",
    "GlobalRanker",
    "active_prospect_controller",
    "ActiveProspectController",
    "discovery_registry",
]
