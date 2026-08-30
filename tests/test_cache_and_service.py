import time
import pytest
import asyncio
from app.services.cache import CacheService
from app.services.rate_limiter import RateLimiter
from app.schemas.profile import ProfileData, Position, Education


def test_cache_service_lru_and_ttl():
    cache = CacheService(max_size=3, default_ttl=1)
    
    p1 = ProfileData(public_id="user1", profile_url="https://www.linkedin.com/in/user1", full_name="User One")
    p2 = ProfileData(public_id="user2", profile_url="https://www.linkedin.com/in/user2", full_name="User Two")
    p3 = ProfileData(public_id="user3", profile_url="https://www.linkedin.com/in/user3", full_name="User Three")
    p4 = ProfileData(public_id="user4", profile_url="https://www.linkedin.com/in/user4", full_name="User Four")

    cache.set("user1", p1)
    cache.set("user2", p2)
    cache.set("user3", p3)

    assert cache.stats["cached_entries"] == 3
    assert cache.get("user1").full_name == "User One"
    assert cache.stats["hits"] == 1

    # Accessing user1 moved it to MRU. Inserting user4 should evict user2 (the LRU item)
    cache.set("user4", p4)
    assert cache.get("user2") is None
    assert cache.get("user1") is not None
    assert cache.get("user3") is not None
    assert cache.get("user4") is not None

    # Test TTL expiration
    time.sleep(1.1)
    assert cache.get("user1") is None
    assert cache.stats["cached_entries"] == 2  # user1 got deleted on expired access
    purged = cache.purge_expired()
    assert purged == 2
    assert cache.stats["cached_entries"] == 0


@pytest.mark.asyncio
async def test_rate_limiter_context_manager():
    limiter = RateLimiter(max_concurrent=2, min_delay_ms=10, max_delay_ms=20)
    async with limiter:
        assert limiter._semaphore._value == 1
    assert limiter._semaphore._value == 2
