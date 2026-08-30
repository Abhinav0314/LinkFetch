import time
from collections import OrderedDict
from typing import Optional, Dict, Any
from app.core.config import settings
from app.schemas.profile import ProfileData


class CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: ProfileData, ttl: int):
        self.data = data
        self.expires_at = time.time() + ttl

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class CacheService:
    """In-memory LRU cache with TTL expiration and active purge."""

    def __init__(self, max_size: int = 500, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def purge_expired(self) -> int:
        """Purges all expired entries from cache and returns count purged."""
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if now > v.expires_at]
        for k in expired_keys:
            del self._cache[k]
        return len(expired_keys)

    def get(self, key: str) -> Optional[ProfileData]:
        """Retrieves an item from cache if present and unexpired, updating its LRU position."""
        norm_key = key.strip().lower()
        entry = self._cache.get(norm_key)

        if not entry:
            self._misses += 1
            return None

        if entry.is_expired:
            del self._cache[norm_key]
            self._misses += 1
            return None

        self._hits += 1
        self._cache.move_to_end(norm_key)
        return entry.data

    def set(self, key: str, data: ProfileData, ttl: Optional[int] = None) -> None:
        """Stores a profile in cache with LRU eviction and TTL."""
        norm_key = key.strip().lower()

        if norm_key in self._cache:
            self._cache.move_to_end(norm_key)
        elif len(self._cache) >= self.max_size:
            # First purge any expired items
            self.purge_expired()
            # If still full, pop least recently used (first item)
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)

        effective_ttl = ttl if ttl is not None else self.default_ttl
        self._cache[norm_key] = CacheEntry(data, effective_ttl)

    def clear(self) -> None:
        """Clears all cached entries."""
        self._cache.clear()

    @property
    def stats(self) -> Dict[str, Any]:
        """Returns diagnostic metrics for the cache."""
        total_requests = self._hits + self._misses
        hit_ratio = round((self._hits / total_requests * 100), 2) if total_requests > 0 else 0.0
        return {
            "cached_entries": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio_percent": hit_ratio,
        }


cache_service = CacheService(
    max_size=settings.CACHE_MAX_SIZE,
    default_ttl=settings.CACHE_TTL_SECONDS,
)
