# Chicago Pickleball Finder

A web app that aggregates pickleball court data across the greater Chicago area from multiple sources, providing a searchable, map-based interface.

## Data Sources

- **Chicago Park District** -- 60 public facilities with addresses, scraped from chicagoparkdistrict.com
- **OpenStreetMap (Overpass API)** -- 691 pickleball features across the metro area, clustered into ~247 locations
- **Nominatim** -- free geocoding to add lat/lng coordinates to address-only records

After deduplication, the database contains **103 unique court locations** across 8 cities.

## Quick Start

```bash
# 1. Install dependencies
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Seed the database (runs all scrapers — takes ~2 minutes)
python scripts/seed.py

# 3. Start the server
uvicorn app.main:app --reload
```

Open http://localhost:8000 in your browser.

## Features

- Full-text search across court names and addresses
- Filter by access type (public / fee / members), indoor/outdoor
- Interactive map with court markers (Leaflet + OpenStreetMap)
- "Courts near me" geolocation with distance sorting
- Court detail modal with phone (click-to-call), directions, and source info
- Weekly automated re-scraping (set `ENABLE_SCHEDULER=true`)

## Deploying to Render

1. Push this repo to GitHub
2. Create a new Web Service on [Render](https://render.com) pointing to the repo
3. Render will use `render.yaml` for configuration
4. The build step runs the seed script; the scheduler keeps data fresh weekly

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./pickleball.db` | Database connection string |
| `ENABLE_SCHEDULER` | `false` | Set to `true` to enable weekly re-scraping |

## Project Structure

```
app/
  main.py              – FastAPI app with lifespan hooks
  models.py            – SQLAlchemy Court model
  database.py          – DB engine & session setup
  scheduler.py         – APScheduler weekly job
  api/routes.py        – REST endpoints (/api/courts, /api/stats)
  scrapers/
    chicago_parks.py   – Chicago Park District scraper
    overpass.py        – OpenStreetMap Overpass API scraper
    geocoder.py        – Nominatim geocoding utility
    runner.py          – Orchestrator + deduplication
frontend/
  index.html           – SPA shell (Tailwind + Leaflet)
  app.js               – Search, filter, map logic
scripts/
  seed.py              – One-time DB seeder
```
