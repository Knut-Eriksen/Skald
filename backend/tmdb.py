"""Optional TMDB boost: extra discovery candidates. Everything works without a key."""
import os

from curl_cffi.requests import AsyncSession

from . import cache

KEY = os.getenv("TMDB_API_KEY", "").strip()


async def recommendations(tmdb_id: int) -> list[int]:
    if not KEY:
        return []
    key = f"tmdbrec:{tmdb_id}"
    if (hit := cache.get(key, 30 * 86400)) is not None:
        return hit
    # v4 read tokens are long JWTs (Bearer); v3 keys go in the query string
    bearer = len(KEY) > 40
    async with AsyncSession(timeout=15) as s:
        r = await s.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}/recommendations",
            params={} if bearer else {"api_key": KEY},
            headers={"Authorization": f"Bearer {KEY}"} if bearer else {},
        )
    if r.status_code != 200:
        return []
    ids = [m["id"] for m in r.json().get("results", [])[:12]]
    cache.set(key, ids)
    return ids
