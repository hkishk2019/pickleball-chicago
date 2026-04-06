"""Targeted scrapers for specific Chicago-area pickleball facilities.

Scrapes individual gym/facility websites for pickleball-specific
schedules, pricing, and temporary court info that generic APIs miss.
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

KNOWN_FACILITIES: list[dict] = [
    {
        "match_names": ["ffc", "fitness formula"],
        "match_cities": ["chicago", "elmhurst", "oak park", "park ridge"],
        "website_url": "https://ffc.com/pickleball/",
        "booking_platform": "ffc",
        "booking_url": "https://ffc.com/pickleball/",
        "access_type": "members",
        "is_temporary": True,
        "schedule_notes": "Converted gym courts; check FFC+ app for current pickleball hours",
    },
    {
        "match_names": ["big city pickle"],
        "website_url": "https://www.bigcitypickle.com/",
        "booking_platform": "podplay",
        "booking_url": "https://bigcitypickle.podplay.app/",
        "access_type": "fee",
    },
    {
        "match_names": ["spf"],
        "website_url": "https://spfchicago.com/",
        "booking_platform": "spf",
        "booking_url": "https://spfchicago.com/",
        "access_type": "fee",
    },
    {
        "match_names": ["chipickle", "chi pickle"],
        "website_url": "https://app.courtreserve.com/Online/Portal/Index/13766",
        "booking_platform": "courtreserve",
        "booking_url": "https://app.courtreserve.com/Online/Portal/Index/13766",
        "access_type": "fee",
    },
    {
        "match_names": ["midtown athletic"],
        "booking_platform": "midtown",
        "access_type": "members",
        "schedule_notes": "Members only; check Midtown app for pickleball schedule",
    },
    {
        "match_names": ["lakeshore sport"],
        "access_type": "members",
        "schedule_notes": "Members only; pickleball schedule varies by location",
    },
    {
        "match_names": ["chicago athletic association"],
        "booking_platform": "grabagame",
        "booking_url": "https://grabagame.com/chicago-athletic-association-pickleball/",
        "access_type": "fee",
    },
    {
        "match_names": ["ymca"],
        "access_type": "members",
        "schedule_notes": "YMCA member access; check location for pickleball hours",
    },
    {
        "match_names": ["mcfetridge"],
        "access_type": "fee",
        "indoor_outdoor": "indoor",
        "schedule_notes": "Chicago Park District indoor facility; drop-in pickleball available",
    },
]


def _matches(court_name: str, court_city: str, facility: dict) -> bool:
    name_low = court_name.lower()
    for pattern in facility.get("match_names", []):
        if pattern in name_low:
            match_cities = facility.get("match_cities")
            if match_cities:
                return court_city.lower() in match_cities
            return True
    return False


def apply_known_facilities(courts: list[dict]) -> list[dict]:
    """Apply known facility metadata to matching courts in place."""
    matched = 0
    for court in courts:
        name = court.get("name", "")
        city = court.get("city", "")
        for facility in KNOWN_FACILITIES:
            if _matches(name, city, facility):
                for key in (
                    "website_url", "booking_url", "booking_platform",
                    "access_type", "is_temporary", "schedule_notes",
                    "indoor_outdoor",
                ):
                    val = facility.get(key)
                    if val is not None and not court.get(key):
                        court[key] = val
                matched += 1
                break

    print(f"  [facilities] matched {matched} courts to known facilities")
    return courts


async def scrape_ffc() -> list[dict]:
    """Scrape FFC pickleball page for location-specific data."""
    courts: list[dict] = []
    url = "https://ffc.com/pickleball/"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True)
        except httpx.HTTPError as exc:
            print(f"  [ffc] request failed: {exc}")
            return courts

    if resp.status_code != 200:
        print(f"  [ffc] HTTP {resp.status_code}")
        return courts

    soup = BeautifulSoup(resp.text, "lxml")
    text = soup.get_text(" ", strip=True)

    price_match = re.search(r"\$(\d+(?:\.\d+)?)\s*(?:per|/)\s*(hour|session|court)", text, re.IGNORECASE)
    price_info = price_match.group(0) if price_match else None

    # Addresses for Nominatim geocoding (page text confirms which clubs offer pickleball)
    ffc_locations: list[tuple[str, str, str, str]] = [
        ("Elmhurst", "670 W North Ave", "Elmhurst", "60126"),
        ("Gold Coast", "1235 N LaSalle St", "Chicago", "60610"),
        ("Oak Park", "1114 Lake St", "Oak Park", "60301"),
        ("Park Ridge", "12 N Northwest Hwy", "Park Ridge", "60068"),
        ("Union Station", "444 W Jackson Blvd", "Chicago", "60606"),
    ]
    text_lower = text.lower()
    for loc, street, city, z in ffc_locations:
        if loc.lower() in text_lower:
            court = {
                "name": f"FFC {loc}",
                "address": street,
                "city": city,
                "zip_code": z,
                "source": "facility",
                "source_id": f"ffc-{loc.lower().replace(' ', '-')}",
                "access_type": "members",
                "is_temporary": True,
                "booking_url": "https://ffc.com/pickleball/",
                "booking_platform": "ffc",
                "website_url": "https://ffc.com/pickleball/",
                "schedule_notes": "Basketball/gym courts converted to pickleball; check FFC+ app for schedule",
                "indoor_outdoor": "indoor",
            }
            if price_info:
                court["price_info"] = price_info
            courts.append(court)

    print(f"  [ffc] found {len(courts)} locations on pickleball page")
    return courts


async def scrape_all_facilities() -> list[dict]:
    """Run all targeted facility scrapers and return new court records."""
    all_courts: list[dict] = []

    print("  Scraping FFC...")
    try:
        ffc_courts = await scrape_ffc()
        all_courts.extend(ffc_courts)
    except Exception as exc:
        print(f"  FFC scraper error: {exc}")

    return all_courts
