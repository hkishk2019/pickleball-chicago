#!/usr/bin/env python3
"""Enrich court records: discover new venues (Yelp + facilities), then fill metadata.

Unlike seed.py (which rebuilds from scratch), discovery inserts additive rows;
enrichment updates existing fields only when blank.
"""

import asyncio
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

from app.database import SessionLocal
from app.models import Court
from app.scrapers.facility_scraper import apply_known_facilities, scrape_all_facilities
from app.scrapers.geocoder import geocode_courts
from app.scrapers.runner import court_from_dict, is_duplicate_of_any
from app.scrapers.yelp_enricher import discover_courts, enrich_all


def _has_coords(d: dict) -> bool:
    return d.get("latitude") is not None and d.get("longitude") is not None


async def run_enrichment():
    db = SessionLocal()
    try:
        existing = db.query(Court).all()
        merged_index = [c.to_dict() for c in existing]
        print(f"Loaded {len(merged_index)} courts from database\n")

        to_insert: list[dict] = []

        print("[1/3] Yelp discovery (pickleball search, ~40 km)...")
        async with httpx.AsyncClient(timeout=25.0) as client:
            discovered = await discover_courts(client)

        await geocode_courts(discovered)

        yelp_new = 0
        for dc in discovered:
            if not _has_coords(dc):
                continue
            if is_duplicate_of_any(dc, merged_index):
                continue
            merged_index.append(dc)
            to_insert.append(dc)
            yelp_new += 1
        print(f"  -> {yelp_new} new Yelp venues (with coordinates, not duplicates)\n")

        print("[2/3] Facility scrapers (FFC, etc.)...")
        facility_rows = await scrape_all_facilities()
        await geocode_courts(facility_rows)

        fac_new = 0
        for fc in facility_rows:
            if not _has_coords(fc):
                print(f"  [skip] no coordinates after geocode: {fc.get('name')}")
                continue
            if is_duplicate_of_any(fc, merged_index):
                continue
            merged_index.append(fc)
            to_insert.append(fc)
            fac_new += 1
        print(f"  -> {fac_new} new facility rows after dedup\n")

        if to_insert:
            print(f"Inserting {len(to_insert)} new court rows...")
            for data in to_insert:
                clean = {k: v for k, v in data.items() if k != "id"}
                db.add(court_from_dict(clean))
            db.commit()
            print("Committed new rows.\n")

        courts = db.query(Court).all()
        court_dicts = [c.to_dict() for c in courts]
        court_ids = {d["id"]: c for d, c in zip(court_dicts, courts)}

        print("[3/3] Known facility metadata + Yelp detail enrichment...")
        apply_known_facilities(court_dicts)
        court_dicts = await enrich_all(court_dicts)

        print("\nSaving updates to database...")
        updated = 0
        enrichable_fields = [
            "phone", "hours", "price_info", "website_url",
            "rating", "review_count", "booking_url", "booking_platform",
            "photo_url", "is_temporary", "schedule_notes",
            "access_type", "indoor_outdoor",
        ]
        for d in court_dicts:
            court_obj = court_ids.get(d.get("id"))
            if not court_obj:
                continue
            changed = False
            for field in enrichable_fields:
                new_val = d.get(field)
                old_val = getattr(court_obj, field, None)
                if new_val is not None and old_val is None:
                    setattr(court_obj, field, new_val)
                    changed = True
            if changed:
                updated += 1

        db.commit()
        print(f"\nDone! Inserted {len(to_insert)} new courts; updated {updated} of {len(courts)} records.")
    finally:
        db.close()


def main():
    print("=== Court Discovery & Enrichment ===\n")

    print("Running migration check...")
    from scripts.migrate import migrate
    migrate()
    print()

    asyncio.run(run_enrichment())


if __name__ == "__main__":
    main()
