import time
from typing import Optional, Dict, Any

class ResearchCache:
    """
    In-memory and TTL-aware cache for fetched sources and verified observations.
    Prevents redundant network round-trips while respecting freshness policies.
    """
    def __init__(self, ttl_seconds: float = 86400.0):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        clean = (url or "").strip().lower()
        entry = self._cache.get(clean)
        if not entry:
            return None
        # Check freshness
        if (time.time() - entry["timestamp"]) > self.ttl_seconds:
            del self._cache[clean]
            return None
        return entry["data"]

    def set(self, url: str, data: Dict[str, Any], content_hash: Optional[str] = None) -> None:
        clean = (url or "").strip().lower()
        self._cache[clean] = {
            "timestamp": time.time(),
            "content_hash": content_hash,
            "data": data
        }

    def invalidate(self, url: str) -> None:
        clean = (url or "").strip().lower()
        if clean in self._cache:
            del self._cache[clean]

    def clear(self) -> None:
        self._cache.clear()

research_cache = ResearchCache()
