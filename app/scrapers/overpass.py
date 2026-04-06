"""Scrape pickleball court data from OpenStreetMap via the Overpass API.

Covers the entire greater Chicago metro area. Individual court nodes that
are close together are clustered into a single location record.
"""
from __future__ import annotations

import math

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding box: roughly greater Chicago metro (south-lat, west-lng, north-lat, east-lng)
BBOX = "41.5,-88.3,42.3,-87.3"

QUERY_TEMPLATE = """
[out:json][timeout:60];
(
  node["sport"~"pickleball"]({bbox});
  way["sport"~"pickleball"]({bbox});
  relation["sport"~"pickleball"]({bbox});
);
out center body;
"""


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _cluster(features: list[dict], radius_m: float = 80.0) -> list[list[dict]]:
    """Group features within `radius_m` of each other into clusters."""
    assigned = [False] * len(features)
    clusters: list[list[dict]] = []

    for i, feat in enumerate(features):
        if assigned[i]:
            continue
        cluster = [feat]
        assigned[i] = True
        for j in range(i + 1, len(features)):
            if assigned[j]:
                continue
            dist = _haversine_m(feat["lat"], feat["lng"], features[j]["lat"], features[j]["lng"])
            if dist < radius_m:
                cluster.append(features[j])
                assigned[j] = True
        clusters.append(cluster)
    return clusters


def _merge_cluster(cluster: list[dict]) -> dict:
    """Merge a cluster of nearby features into one location record."""
    name = None
    tags_merged: dict = {}
    lats, lngs = [], []
    court_count = len(cluster)

    for feat in cluster:
        lats.append(feat["lat"])
        lngs.append(feat["lng"])
        for k, v in feat.get("tags", {}).items():
            if v and (k not in tags_merged or not tags_merged[k]):
                tags_merged[k] = v
        if feat.get("tags", {}).get("name") and not name:
            name = feat["tags"]["name"]

    if not name:
        street = tags_merged.get("addr:street", "")
        housenumber = tags_merged.get("addr:housenumber", "")
        city = tags_merged.get("addr:city", "")
        if street:
            name = f"{housenumber} {street}".strip()
            if city:
                name += f", {city}"
        else:
            name = f"Pickleball Courts ({round(sum(lats)/len(lats), 4)}, {round(sum(lngs)/len(lngs), 4)})"

    address_parts = []
    if tags_merged.get("addr:housenumber"):
        address_parts.append(tags_merged["addr:housenumber"])
    if tags_merged.get("addr:street"):
        address_parts.append(tags_merged["addr:street"])
    address = " ".join(address_parts)

    surface = tags_merged.get("surface", "").lower()
    if surface not in ("hard", "asphalt", "concrete", "wood", "clay"):
        surface = None

    access_raw = tags_merged.get("access", "").lower()
    if access_raw in ("yes", "public", "permissive"):
        access_type = "public"
    elif access_raw in ("private", "no"):
        access_type = "private"
    elif access_raw in ("customers",):
        access_type = "fee"
    else:
        access_type = None

    return {
        "name": name,
        "address": address,
        "city": tags_merged.get("addr:city", ""),
        "zip_code": tags_merged.get("addr:postcode", ""),
        "latitude": sum(lats) / len(lats),
        "longitude": sum(lngs) / len(lngs),
        "phone": tags_merged.get("phone"),
        "num_courts": court_count,
        "indoor_outdoor": "indoor" if tags_merged.get("indoor") == "yes" else "outdoor",
        "access_type": access_type,
        "surface_type": surface,
        "has_lights": tags_merged.get("lit") == "yes",
        "hours": tags_merged.get("opening_hours"),
        "price_info": "Free" if tags_merged.get("fee") == "no" else None,
        "website_url": tags_merged.get("website"),
        "source": "osm",
        "source_id": f"osm-cluster-{round(sum(lats)/len(lats),5)}-{round(sum(lngs)/len(lngs),5)}",
    }


async def scrape_all() -> list[dict]:
    query = QUERY_TEMPLATE.format(bbox=BBOX)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": "PickleballChicagoFinder/1.0"},
            )
        except httpx.HTTPError as exc:
            print(f"  [overpass] request failed: {exc}")
            return []

    if resp.status_code != 200:
        print(f"  [overpass] HTTP {resp.status_code}")
        return []

    try:
        data = resp.json()
    except ValueError:
        print("  [overpass] invalid JSON")
        return []

    elements = data.get("elements", [])
    print(f"  [overpass] raw features: {len(elements)}")

    features = []
    for el in elements:
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        features.append({"lat": lat, "lng": lng, "tags": el.get("tags", {})})

    clusters = _cluster(features)
    courts = [_merge_cluster(c) for c in clusters]
    print(f"  [overpass] clustered into {len(courts)} locations")
    return courts
