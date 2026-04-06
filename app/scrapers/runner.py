"""Orchestrates all scrapers, deduplicates, geocodes, and saves to the database."""
from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Court

from . import chicago_parks, overpass
from .geocoder import geocode_courts


def _normalize_name(name: str) -> str:
    low = name.lower().strip()
    low = re.sub(r"\b(park|courts?|pickleball|fieldhouse|field house|gymnasium)\b", "", low)
    low = re.sub(r"[^a-z0-9]", "", low)
    return low


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _name_similarity(a: str, b: str) -> float:
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.8
    common = len(set(na) & set(nb))
    total = max(len(set(na)), len(set(nb)))
    return common / total if total else 0.0


def _is_duplicate(a: dict, b: dict, distance_threshold: float = 150.0) -> bool:
    a_lat, a_lng = a.get("latitude"), a.get("longitude")
    b_lat, b_lng = b.get("latitude"), b.get("longitude")

    if all(v is not None for v in (a_lat, a_lng, b_lat, b_lng)):
        dist = _haversine_m(a_lat, a_lng, b_lat, b_lng)
        if dist < distance_threshold:
            name_sim = _name_similarity(a.get("name", ""), b.get("name", ""))
            if name_sim > 0.4:
                return True
            if dist < 50:
                return True

    if _name_similarity(a.get("name", ""), b.get("name", "")) > 0.85:
        a_city = (a.get("city") or "").lower().strip()
        b_city = (b.get("city") or "").lower().strip()
        if a_city == b_city or not a_city or not b_city:
            return True

    return False


def is_duplicate_of_any(candidate: dict, others: list[dict]) -> bool:
    """True if candidate is considered the same venue as any dict in others (name + distance)."""
    for other in others:
        if _is_duplicate(candidate, other):
            return True
    return False


def _merge(primary: dict, secondary: dict) -> dict:
    merged = dict(primary)
    for key, val in secondary.items():
        if val is not None and not merged.get(key):
            merged[key] = val
    return merged


SOURCE_PRIORITY = {"cpd": 0, "osm": 1}


def deduplicate(courts: list[dict]) -> list[dict]:
    courts.sort(key=lambda c: SOURCE_PRIORITY.get(c.get("source", ""), 99))

    merged: list[dict] = []
    for court in courts:
        found = False
        for i, existing in enumerate(merged):
            if _is_duplicate(court, existing):
                merged[i] = _merge(existing, court)
                found = True
                break
        if not found:
            merged.append(court)

    return merged


def _court_from_dict(data: dict) -> Court:
    fields = {
        "name", "address", "city", "zip_code", "latitude", "longitude",
        "phone", "num_courts", "indoor_outdoor", "access_type", "surface_type",
        "net_type", "has_lights", "hours", "price_info", "description",
        "website_url", "source", "source_id",
        "rating", "review_count", "booking_url", "booking_platform",
        "photo_url", "is_temporary", "schedule_notes",
    }
    kwargs = {k: v for k, v in data.items() if k in fields and v is not None}
    kwargs.setdefault("address", "")
    kwargs.setdefault("city", "")
    kwargs.setdefault("source", "unknown")
    kwargs["last_updated"] = datetime.now(timezone.utc)
    return Court(**kwargs)


def court_from_dict(data: dict) -> Court:
    """Build a Court ORM row from a scraper/enrichment dict (for inserts outside full seed)."""
    return _court_from_dict(data)


async def _run_scrapers() -> list[dict]:
    print("Starting scrapers...")
    all_courts: list[dict] = []

    print("[1/2] Chicago Park District")
    try:
        cpd = await chicago_parks.scrape_all()
        all_courts.extend(cpd)
    except Exception as exc:
        print(f"  Chicago Parks error: {exc}")

    print("[2/2] OpenStreetMap (Overpass API)")
    try:
        osm = await overpass.scrape_all()
        all_courts.extend(osm)
    except Exception as exc:
        print(f"  Overpass error: {exc}")

    print(f"\nTotal raw courts: {len(all_courts)}")
    merged = deduplicate(all_courts)
    print(f"After dedup: {len(merged)}")

    print("\nGeocoding courts without coordinates...")
    merged = await geocode_courts(merged)

    return merged


def save_to_db(db: Session, courts: list[dict]):
    db.query(Court).delete()
    for data in courts:
        db.add(_court_from_dict(data))
    db.commit()
    print(f"Saved {len(courts)} courts to database")


def run_full_scrape(db: Session):
    courts = asyncio.run(_run_scrapers())
    save_to_db(db, courts)
    return len(courts)
