"""Enrich court records with data from the Yelp Fusion API.

Requires YELP_API_KEY: set in the environment or in repo-root `.env` (loaded by scripts/enrich.py).
Free tier: 5,000 API calls/day -- more than enough for ~100 courts.
"""
from __future__ import annotations

import asyncio
import math
import os
import re

import httpx

def _api_key() -> str:
    """Read key at call time so callers can load_dotenv() before first use."""
    return (os.getenv("YELP_API_KEY", "") or "").strip()
SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
DETAIL_URL = "https://api.yelp.com/v3/businesses"
DELAY = 0.5

# Chicago center + max Yelp search radius (meters)
CHICAGO_LAT = 41.8781
CHICAGO_LNG = -87.6298
DISCOVERY_RADIUS_M = 40_000
DISCOVERY_PAGE = 50
DISCOVERY_MAX_OFFSET = 950  # Yelp caps total results; stay under 1000 with limit 50


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _name_similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.8
    common = len(set(na) & set(nb))
    total = max(len(set(na)), len(set(nb)))
    return common / total if total else 0.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _format_hours(hours_data: list[dict]) -> str | None:
    if not hours_data:
        return None
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    lines = []
    for h in hours_data:
        if h.get("hours_type") != "REGULAR":
            continue
        for slot in h.get("open", []):
            day_idx = slot.get("day", 0)
            day_name = days[day_idx] if day_idx < 7 else "?"
            start = slot.get("start", "")
            end = slot.get("end", "")
            if start and end:
                s = f"{start[:2]}:{start[2:]}" if len(start) == 4 else start
                e = f"{end[:2]}:{end[2:]}" if len(end) == 4 else end
                lines.append(f"{day_name} {s}-{e}")
    return "; ".join(lines) if lines else None


def _yelp_biz_to_court(biz: dict) -> dict:
    """Map a Yelp Fusion business (search or detail) to our court dict shape."""
    loc = biz.get("location") or {}
    coords = biz.get("coordinates") or {}
    lat = coords.get("latitude")
    lng = coords.get("longitude")
    addr1 = (loc.get("address1") or "").strip()
    city = (loc.get("city") or "").strip()
    z = (loc.get("zip_code") or "").strip()
    return {
        "name": (biz.get("name") or "").strip() or "Unknown",
        "address": addr1,
        "city": city or "Chicago",
        "zip_code": z or None,
        "latitude": lat,
        "longitude": lng,
        "phone": biz.get("display_phone"),
        "rating": biz.get("rating"),
        "review_count": biz.get("review_count"),
        "photo_url": biz.get("image_url"),
        "price_info": biz.get("price"),
        "website_url": biz.get("url"),
        "source": "yelp",
        "source_id": biz.get("id"),
    }


async def discover_courts(client: httpx.AsyncClient) -> list[dict]:
    """Paginated Yelp search for pickleball near Chicago; returns deduped court dicts by business id."""
    if not _api_key():
        print("  [yelp] YELP_API_KEY not set -- skipping discovery")
        return []

    headers = {"Authorization": f"Bearer {_api_key()}"}
    seen_ids: set[str] = set()
    raw: list[dict] = []
    offset = 0

    while offset <= DISCOVERY_MAX_OFFSET:
        params = {
            "term": "pickleball",
            "latitude": CHICAGO_LAT,
            "longitude": CHICAGO_LNG,
            "radius": DISCOVERY_RADIUS_M,
            "limit": DISCOVERY_PAGE,
            "offset": offset,
            "sort_by": "distance",
        }
        try:
            resp = await client.get(SEARCH_URL, headers=headers, params=params)
        except httpx.HTTPError as exc:
            print(f"  [yelp] discovery request failed at offset={offset}: {exc}")
            break
        await asyncio.sleep(DELAY)
        if resp.status_code != 200:
            print(f"  [yelp] discovery HTTP {resp.status_code} at offset={offset}")
            break
        batch = resp.json().get("businesses") or []
        if not batch:
            break
        for biz in batch:
            bid = biz.get("id")
            if not bid or bid in seen_ids:
                continue
            seen_ids.add(bid)
            raw.append(biz)
        if len(batch) < DISCOVERY_PAGE:
            break
        offset += DISCOVERY_PAGE

    courts: list[dict] = []
    for biz in raw:
        c = _yelp_biz_to_court(biz)
        if c.get("latitude") is not None and c.get("longitude") is not None:
            courts.append(c)
        elif c.get("address"):
            courts.append(c)
    print(f"  [yelp] discovery: {len(courts)} businesses with coordinates or address")
    return courts


async def _search_business(
    client: httpx.AsyncClient, name: str, lat: float, lng: float
) -> dict | None:
    """Search Yelp for a business matching the court name near the given coordinates."""
    headers = {"Authorization": f"Bearer {_api_key()}"}
    params = {
        "term": name,
        "latitude": lat,
        "longitude": lng,
        "radius": 800,
        "limit": 5,
        "sort_by": "distance",
    }

    try:
        resp = await client.get(SEARCH_URL, headers=headers, params=params)
    except httpx.HTTPError:
        return None

    if resp.status_code != 200:
        return None

    businesses = resp.json().get("businesses", [])
    if not businesses:
        return None

    best = None
    best_score = 0.0
    for biz in businesses:
        sim = _name_similarity(name, biz.get("name", ""))
        coords = biz.get("coordinates", {})
        biz_lat = coords.get("latitude")
        biz_lng = coords.get("longitude")
        dist_penalty = 0.0
        if biz_lat and biz_lng:
            dist = _haversine_m(lat, lng, biz_lat, biz_lng)
            dist_penalty = min(dist / 2000, 0.3)
        score = sim - dist_penalty
        if score > best_score:
            best_score = score
            best = biz

    if best_score < 0.3:
        return None
    return best


async def _get_details(client: httpx.AsyncClient, biz_id: str) -> dict | None:
    headers = {"Authorization": f"Bearer {_api_key()}"}
    try:
        resp = await client.get(f"{DETAIL_URL}/{biz_id}", headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()


async def enrich_court(client: httpx.AsyncClient, court: dict) -> dict:
    """Enrich a single court dict with Yelp data. Returns updated dict."""
    name = court.get("name", "")
    lat = court.get("latitude")
    lng = court.get("longitude")
    if not name or lat is None or lng is None:
        return court

    biz = await _search_business(client, name, lat, lng)
    await asyncio.sleep(DELAY)
    if not biz:
        return court

    if not court.get("phone") and biz.get("display_phone"):
        court["phone"] = biz["display_phone"]

    if biz.get("rating"):
        court["rating"] = biz["rating"]
    if biz.get("review_count"):
        court["review_count"] = biz["review_count"]

    if not court.get("photo_url") and biz.get("image_url"):
        court["photo_url"] = biz["image_url"]

    if not court.get("price_info") and biz.get("price"):
        court["price_info"] = biz["price"]

    if not court.get("website_url") and biz.get("url"):
        court["website_url"] = biz["url"]

    biz_id = biz.get("id")
    if biz_id and not court.get("hours"):
        details = await _get_details(client, biz_id)
        await asyncio.sleep(DELAY)
        if details:
            hours_str = _format_hours(details.get("hours", []))
            if hours_str:
                court["hours"] = hours_str

    return court


async def enrich_all(courts: list[dict]) -> list[dict]:
    if not _api_key():
        print("  [yelp] YELP_API_KEY not set -- skipping enrichment")
        print("  [yelp] Get a free key at https://fusion.yelp.com")
        return courts

    enriched = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i, court in enumerate(courts):
            before_phone = court.get("phone")
            before_rating = court.get("rating")
            court = await enrich_court(client, court)
            courts[i] = court
            if court.get("phone") != before_phone or court.get("rating") != before_rating:
                enriched += 1
                print(f"  [yelp] + {court.get('name', '?')}: rating={court.get('rating')}, phone={court.get('phone')}")

    print(f"  [yelp] enriched {enriched} of {len(courts)} courts")
    return courts
