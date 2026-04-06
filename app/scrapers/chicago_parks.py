from __future__ import annotations

import asyncio
import re
from urllib.parse import unquote_plus

import httpx
from bs4 import BeautifulSoup

URL = "https://www.chicagoparkdistrict.com/facilities/pickleball-courts"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _parse_google_maps_address(href: str) -> dict:
    m = re.search(r"[?&]q=([^&]+)", href)
    if not m:
        return {}
    raw = unquote_plus(m.group(1))
    parts = [p.strip() for p in raw.split(",")]
    result: dict = {"address": parts[0] if parts else raw, "city": "Chicago"}
    if len(parts) >= 3 and parts[-1].strip().isdigit():
        result["zip_code"] = parts[-1].strip()
    elif len(parts) >= 2:
        last = parts[-1].strip()
        if last.isdigit() and len(last) == 5:
            result["zip_code"] = last
    return result


async def scrape_all() -> list[dict]:
    courts: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(URL, headers=HEADERS, follow_redirects=True)
        except httpx.HTTPError as exc:
            print(f"  [chicago_parks] request failed: {exc}")
            return courts

    if resp.status_code != 200:
        print(f"  [chicago_parks] HTTP {resp.status_code}")
        return courts

    soup = BeautifulSoup(resp.text, "lxml")

    for heading in soup.find_all(re.compile(r"^h[2-4]$")):
        name = heading.get_text(strip=True)
        if not name:
            continue
        name = re.sub(r"\s*\|\s*", " - ", name)
        name = re.sub(r"Pickleball\s*(?:/\s*)?Tennis\s*Courts?", "", name, flags=re.IGNORECASE)
        name = re.sub(r"Pickleball\s*Courts?", "", name, flags=re.IGNORECASE)
        name = re.sub(r"Pickleball", "", name, flags=re.IGNORECASE)
        name = re.sub(r"^\s*[-–—|:]\s*", "", name).strip()
        name = re.sub(r"\s*[-–—|:]\s*$", "", name).strip()

        if not name or len(name) < 3:
            continue

        maps_link = heading.find_next("a", href=re.compile(r"google\.com/maps"))
        if not maps_link:
            continue

        addr_data = _parse_google_maps_address(maps_link["href"])
        if not addr_data.get("address"):
            continue

        court = {
            "name": name,
            "source": "cpd",
            "source_id": f"cpd-{name.lower().replace(' ', '-')}",
            "city": "Chicago",
            "access_type": "public",
            **addr_data,
        }
        courts.append(court)

    seen = set()
    unique: list[dict] = []
    for c in courts:
        key = (c["name"].lower(), c.get("address", "").lower())
        if key not in seen:
            seen.add(key)
            unique.append(c)

    print(f"  [chicago_parks] scraped {len(unique)} facilities")
    return unique
