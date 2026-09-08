import os
import yaml
from typing import Dict, Any, List, Optional
from app.campaigns.models import CountryProfileDTO, RolloutLevelDTO, RolloutConfigDTO
from app.core.logging import logger

DEFAULT_18_COUNTRIES: List[Dict[str, Any]] = [
    {"code": "US", "name": "United States", "timezone": "America/New_York", "currency": "USD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "CAN-SPAM", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "UK", "name": "United Kingdom", "timezone": "Europe/London", "currency": "GBP", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "UK-GDPR / PECR", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "CA", "name": "Canada", "timezone": "America/Toronto", "currency": "CAD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "CASL", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "AU", "name": "Australia", "timezone": "Australia/Sydney", "currency": "AUD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "Spam Act 2003", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "AE", "name": "United Arab Emirates", "timezone": "Asia/Dubai", "currency": "AED", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "UAE Federal Data Protection", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "SA", "name": "Saudi Arabia", "timezone": "Asia/Riyadh", "currency": "SAR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "Saudi PDPL", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "DE", "name": "Germany", "timezone": "Europe/Berlin", "currency": "EUR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "EU-GDPR / UWG", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "FR", "name": "France", "timezone": "Europe/Paris", "currency": "EUR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "EU-GDPR / CNIL", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "NL", "name": "Netherlands", "timezone": "Europe/Amsterdam", "currency": "EUR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "EU-GDPR / Telecommunicatiewet", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "SE", "name": "Sweden", "timezone": "Europe/Stockholm", "currency": "SEK", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "EU-GDPR / Marketing Act", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "SG", "name": "Singapore", "timezone": "Asia/Singapore", "currency": "SGD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "Spam Control Act / PDPA", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "JP", "name": "Japan", "timezone": "Asia/Tokyo", "currency": "JPY", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "Specified Electronic Mail Act", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "NZ", "name": "New Zealand", "timezone": "Pacific/Auckland", "currency": "NZD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "Unsolicited Electronic Messages Act 2007", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "IE", "name": "Ireland", "timezone": "Europe/Dublin", "currency": "EUR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "EU-GDPR / ePrivacy SI 336", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "ES", "name": "Spain", "timezone": "Europe/Madrid", "currency": "EUR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "EU-GDPR / LSSI-CE", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "IT", "name": "Italy", "timezone": "Europe/Rome", "currency": "EUR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "EU-GDPR / Codice Privacy", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "CH", "name": "Switzerland", "timezone": "Europe/Zurich", "currency": "CHF", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 17, "compliance_framework": "Swiss FADP / UWG Art 3", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "QA", "name": "Qatar", "timezone": "Asia/Qatar", "currency": "QAR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "Law No. 13 of 2016 PDP", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "KW", "name": "Kuwait", "timezone": "Asia/Kuwait", "currency": "KWD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "CITRA Regulatory Framework / E-Commerce Law", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "OM", "name": "Oman", "timezone": "Asia/Muscat", "currency": "OMR", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "Royal Decree 6/2022 (PDPL)", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "BH", "name": "Bahrain", "timezone": "Asia/Bahrain", "currency": "BHD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "Law No. 30 of 2018 (PDPL)", "requires_postal_address": True, "requires_opt_out_link": True},
    {"code": "JO", "name": "Jordan", "timezone": "Asia/Amman", "currency": "JOD", "daily_quota": 10, "enabled": True, "sending_window_start": 9, "sending_window_end": 18, "compliance_framework": "Personal Data Protection Law 2023", "requires_postal_address": True, "requires_opt_out_link": True}
]

DEFAULT_ROLLOUT_LEVELS: Dict[int, Dict[str, Any]] = {
    0: {"name": "Simulation (Dry Run)", "daily_max_real_emails": 0, "description": "Complete pipeline verification with zero real external socket dispatch."},
    1: {"name": "Canary Test", "daily_max_real_emails": 1, "description": "Strict single verified lead test with mandatory CEO sign-off."},
    2: {"name": "First Batch", "daily_max_real_emails": 5, "description": "Low-rate validation across verified leads."},
    3: {"name": "1 Country Live", "daily_max_real_emails": 10, "description": "Single-country full quota proof."},
    4: {"name": "Multi-Corridor Scaling", "daily_max_real_emails": 20, "description": "Gradual expansion across active corridors (20/day)."},
    5: {"name": "Regional Expansion", "daily_max_real_emails": 50, "description": "Regional expansion across active international corridors (50/day)."},
    6: {"name": "Broad International Rollout", "daily_max_real_emails": 100, "description": "Broad rollout across international corridors (100/day)."},
    7: {"name": "All 18 Countries Live", "daily_max_real_emails": 180, "description": "10 qualified prospects/day across all 18 configured international countries (180/day)."}
}


class CampaignConfigLoader:
    """Loads and caches international campaign configurations from YAML."""

    # First-client live validation guard: By default, rollout level cannot exceed Level 1 (Canary: max 1 real send)
    FIRST_CLIENT_VALIDATION_ACTIVE: bool = True

    def __init__(self, config_path: str = "config/international_campaigns.yaml"):
        self.config_path = config_path
        self._current_rollout_level: int = 0
        self._load_config()

    def _load_config(self) -> None:
        self._countries: Dict[str, CountryProfileDTO] = {}
        self._rollout_levels: Dict[int, RolloutLevelDTO] = {}

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

                # Rollout config
                rollout_data = data.get("rollout", {})
                loaded_level = int(rollout_data.get("current_level", 0))
                if self.FIRST_CLIENT_VALIDATION_ACTIVE and loaded_level > 1:
                    logger.warning(f"[CampaignConfigLoader] Clamping rollout level from {loaded_level} to Level 1 (Canary 1-send lock for live validation).")
                    loaded_level = 1
                self._current_rollout_level = loaded_level

                for lvl, info in rollout_data.get("levels", {}).items():
                    self._rollout_levels[int(lvl)] = RolloutLevelDTO(
                        level=int(lvl),
                        name=info.get("name", f"Level {lvl}"),
                        daily_max_real_emails=int(info.get("daily_max_real_emails", 0)),
                        description=info.get("description", "")
                    )

                # Country configs
                for c in data.get("countries", []):
                    dto = CountryProfileDTO(**c)
                    self._countries[dto.code.upper()] = dto

                logger.info(f"[CampaignConfigLoader] Loaded {len(self._countries)} international country profiles from {self.config_path}")
                return
            except Exception as e:
                logger.error(f"[CampaignConfigLoader] Error loading {self.config_path}: {e}")

        # Fallback to in-code defaults
        for c in DEFAULT_18_COUNTRIES:
            dto = CountryProfileDTO(**c)
            self._countries[dto.code.upper()] = dto

        for lvl, info in DEFAULT_ROLLOUT_LEVELS.items():
            self._rollout_levels[lvl] = RolloutLevelDTO(
                level=lvl,
                name=info["name"],
                daily_max_real_emails=info["daily_max_real_emails"],
                description=info["description"]
            )

    def list_countries(self) -> List[CountryProfileDTO]:
        return list(self._countries.values())

    def get_country(self, code: str) -> Optional[CountryProfileDTO]:
        return self._countries.get((code or "").strip().upper())

    def get_rollout_config(self) -> RolloutConfigDTO:
        lvl = self._rollout_levels.get(self._current_rollout_level)
        return RolloutConfigDTO(
            current_level=self._current_rollout_level,
            current_level_name=lvl.name if lvl else f"Level {self._current_rollout_level}",
            daily_max_real_emails=lvl.daily_max_real_emails if lvl else 0,
            is_simulation=self._current_rollout_level == 0,
            levels=list(self._rollout_levels.values())
        )

    def set_rollout_level(self, level: int, allow_bulk: bool = False) -> RolloutConfigDTO:
        if level not in self._rollout_levels:
            raise ValueError(f"Invalid rollout level {level}. Allowed levels are 0 through 7.")
        if level > 1 and getattr(self, "FIRST_CLIENT_VALIDATION_ACTIVE", True) and not allow_bulk:
            raise ValueError(
                f"First live validation is strictly capped at 1 real send (Level 1: Canary). "
                f"Advancing to Level {level} (bulk multi-country dispatch) is blocked to protect sender reputation prior to CEO review."
            )
        self._current_rollout_level = level
        logger.info(f"[CampaignConfigLoader] Rollout level set to {level} ({self._rollout_levels[level].name})")
        return self.get_rollout_config()


campaign_config_loader = CampaignConfigLoader()
