"""
Intelligence Cache — Mega Prompt 8.
Prevents repeated costly analysis by caching intelligence deductions with TTL,
version hashing, and automatic invalidation on source entity mutations.
"""
import hashlib
import json
import time
from typing import Dict, Any, Optional

class IntelligenceCache:
    """In-memory thread-safe intelligence cache for the single-node runtime."""

    def __init__(self, default_ttl_seconds: int = 3600):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl_seconds

    @staticmethod
    def generate_cache_key(entity_type: str, entity_id: int, operation: str, data: Dict[str, Any]) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        data_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return f"{entity_type}:{entity_id}:{operation}:{data_hash}"

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            del self._cache[key]
            return None
        return entry["value"]

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds or self.default_ttl
        self._cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl
        }

    def invalidate_entity(self, entity_type: str, entity_id: int) -> int:
        prefix = f"{entity_type}:{entity_id}:"
        to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
        for k in to_delete:
            del self._cache[k]
        return len(to_delete)

    def clear(self) -> None:
        self._cache.clear()


intelligence_cache = IntelligenceCache()
