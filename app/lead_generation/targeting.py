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
    max_prospects_per_cycle: int = Field(default=50, ge=1, le=500, description="Maximum prospects to process per prospecting run")

class CountryConfig(BaseModel):
    code: str
    name: str
    currency: str = "USD"
    regions: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)

class NicheConfig(BaseModel):
    name: str
    slug: str
    category: str
    min_estimated_service_value: int = 1000
    typical_range: List[int] = Field(default_factory=lambda: [1000, 3000])
    keywords: List[str] = Field(default_factory=list)

class TargetingConfig(BaseModel):
    country: str = Field(default="United States")
    country_code: str = Field(default="US")
    regions: List[str] = Field(default_factory=lambda: ["Texas"])
    cities: List[str] = Field(default_factory=lambda: ["Austin", "Dallas", "Houston"])
    niches: List[str] = Field(default_factory=lambda: ["HVAC"])
    filters: TargetingFilters = Field(default_factory=TargetingFilters)
    commercial: CommercialConfig = Field(default_factory=CommercialConfig)
    # Global multi-market support
    available_countries: List[CountryConfig] = Field(default_factory=list)
    available_niches: List[NicheConfig] = Field(default_factory=list)

def load_targeting_config(config_path: Optional[str] = None) -> TargetingConfig:
    """Loads and validates targeting and commercial configuration from YAML file."""
    # Check for markets.yaml first, fallback to targeting.yaml
    if config_path is None:
        if os.path.exists("config/markets.yaml"):
            config_path = "config/markets.yaml"
        elif os.path.exists("config/targeting.yaml"):
            config_path = "config/targeting.yaml"
        else:
            return TargetingConfig()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Targeting configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}

    # Handle global markets.yaml schema
    if "markets" in data:
        m_data = data["markets"]
        countries = [CountryConfig(**c) for c in m_data.get("countries", [])]
        niches = [NicheConfig(**n) for n in data.get("niches", [])]
        comm_dict = data.get("commercial", {})
        filt_dict = data.get("filters", {})

        # Default to first country / cities if not explicitly overridden
        primary_country = countries[0] if countries else CountryConfig(code="US", name="United States", cities=["Austin"])
        
        return TargetingConfig(
            country=primary_country.name,
            country_code=primary_country.code,
            regions=primary_country.regions or ["Texas"],
            cities=primary_country.cities or ["Austin", "Dallas", "Houston"],
            niches=[n.name for n in niches] if niches else ["HVAC"],
            filters=TargetingFilters(**filt_dict),
            commercial=CommercialConfig(**comm_dict),
            available_countries=countries,
            available_niches=niches
        )

    # Handle legacy / flat targeting block if present
    if "targeting" in data and isinstance(data["targeting"], dict):
        nested = data.pop("targeting")
        for k, v in nested.items():
            if k not in data:
                data[k] = v

    return TargetingConfig(**data)
