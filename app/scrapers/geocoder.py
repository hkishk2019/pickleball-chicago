"""Geocode addresses using the free Nominatim (OpenStreetMap) API."""
from __future__ import annotations

import asyncio

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "PickleballChicagoFinder/1.0"}
DELAY = 1.1  # Nominatim requires max 1 request/sec


async def geocode(address: str, city: str = "", state: str = "IL") -> dict | None:
    """Return {"lat": float, "lng": float} for an address, or None."""
    query = f"{address}, {city}, {state}" if city else f"{address}, {state}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
                headers=HEADERS,
            )
        except httpx.HTTPError:
            return None

    if resp.status_code != 200:
        return None

    results = resp.json()
    if not results:
        return None
    return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}


async def geocode_courts(courts: list[dict]) -> list[dict]:
    """Add lat/lng to courts that have an address but no coordinates."""
    enriched = 0
    for court in courts:
        if court.get("latitude") and court.get("longitude"):
            continue
        if not court.get("address"):
            continue

        coords = await geocode(court["address"], court.get("city", ""))
        if coords:
            court["latitude"] = coords["lat"]
            court["longitude"] = coords["lng"]
            enriched += 1

        await asyncio.sleep(DELAY)

    print(f"  [geocoder] enriched {enriched} courts with coordinates")
    return courts
