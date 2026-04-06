from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Court

router = APIRouter(prefix="/api")


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/courts")
def list_courts(
    q: Optional[str] = Query(None, description="Text search on name or address"),
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
    indoor: Optional[bool] = None,
    outdoor: Optional[bool] = None,
    access: Optional[str] = Query(None, description="public, fee, or members"),
    surface: Optional[str] = None,
    lat: Optional[float] = Query(None, description="Latitude for nearby search"),
    lng: Optional[float] = Query(None, description="Longitude for nearby search"),
    radius: float = Query(16000, description="Search radius in meters (default 16km / ~10mi)"),
    sort: str = Query("name", description="Sort by: name, distance, courts"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Court)

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            (Court.name.ilike(pattern)) | (Court.address.ilike(pattern))
        )

    if city:
        query = query.filter(Court.city.ilike(f"%{city}%"))

    if zip_code:
        query = query.filter(Court.zip_code == zip_code)

    if access:
        query = query.filter(Court.access_type == access.lower())

    if surface:
        query = query.filter(Court.surface_type == surface.lower())

    if indoor is True:
        query = query.filter(Court.indoor_outdoor.in_(["indoor", "both"]))

    if outdoor is True:
        query = query.filter(Court.indoor_outdoor.in_(["outdoor", "both"]))

    courts = query.all()

    if lat is not None and lng is not None:
        courts = [
            c for c in courts
            if c.latitude is not None
            and c.longitude is not None
            and _haversine_m(lat, lng, c.latitude, c.longitude) <= radius
        ]

    results = []
    for c in courts:
        d = c.to_dict()
        if lat is not None and lng is not None and c.latitude and c.longitude:
            d["distance_m"] = round(_haversine_m(lat, lng, c.latitude, c.longitude))
        results.append(d)

    if sort == "distance" and lat is not None:
        results.sort(key=lambda r: r.get("distance_m", float("inf")))
    elif sort == "courts":
        results.sort(key=lambda r: -(r.get("num_courts") or 0))
    else:
        results.sort(key=lambda r: r.get("name", "").lower())

    total = len(results)
    results = results[offset : offset + limit]
    return {"total": total, "courts": results}


@router.get("/courts/{court_id}")
def get_court(court_id: int, db: Session = Depends(get_db)):
    court = db.query(Court).filter(Court.id == court_id).first()
    if not court:
        return {"error": "Court not found"}, 404
    return court.to_dict()


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(sqlfunc.count(Court.id)).scalar() or 0
    total_court_count = db.query(sqlfunc.sum(Court.num_courts)).scalar() or 0
    cities = db.query(sqlfunc.count(sqlfunc.distinct(Court.city))).scalar() or 0

    access_counts = {}
    for row in db.query(Court.access_type, sqlfunc.count(Court.id)).group_by(Court.access_type).all():
        if row[0]:
            access_counts[row[0]] = row[1]

    indoor_outdoor = {}
    for row in db.query(Court.indoor_outdoor, sqlfunc.count(Court.id)).group_by(Court.indoor_outdoor).all():
        if row[0]:
            indoor_outdoor[row[0]] = row[1]

    return {
        "total_locations": total,
        "total_courts": total_court_count,
        "cities": cities,
        "by_access": access_counts,
        "by_type": indoor_outdoor,
    }
