import os
import yaml
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class TargetingFilters(BaseModel):
    min_rating: float = Field(default=3.5, ge=0.0, le=5.0)
    max_rating: float = Field(default=5.0, ge=0.0, le=5.0)
    min_reviews: int = Field(default=0, ge=0)
    require_website: bool = Field(default=True)
    require_phone: bool = Field(default=False)
    target_results_per_city: int = Field(default=20, ge=1)

class CommercialConfig(BaseModel):
    minimum_target_service_value_usd: int = Field(default=1000, description="Minimum contract service size")
    high_value_buyer_threshold: float = Field(default=75.0, ge=0.0, le=100.0, description="Buyer score threshold for priority pipeline")
    opportunity_score_threshold: float = Field(default=65.0, ge=0.0, le=100.0, description="Opportunity score threshold for priority pipeline")

class TargetingConfig(BaseModel):
    country: str = Field(default="United States")
    country_code: str = Field(default="US")
    regions: List[str] = Field(default_factory=lambda: ["Texas"])
    cities: List[str] = Field(default_factory=lambda: ["Austin", "Dallas", "Houston"])
    niches: List[str] = Field(default_factory=lambda: ["HVAC"])
    filters: TargetingFilters = Field(default_factory=TargetingFilters)
    commercial: CommercialConfig = Field(default_factory=CommercialConfig)

def load_targeting_config(config_path: str = "config/targeting.yaml") -> TargetingConfig:
    """Loads and validates targeting and commercial configuration from YAML file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Targeting configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}

    # Handle nested targeting block if present
    if "targeting" in data and isinstance(data["targeting"], dict):
        nested = data.pop("targeting")
        for k, v in nested.items():
            if k not in data:
                data[k] = v

    return TargetingConfig(**data)
