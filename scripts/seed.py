#!/usr/bin/env python3
"""One-time seed script: runs all scrapers and populates the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine
from app.scrapers.runner import run_full_scrape


def main():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        count = run_full_scrape(db)
        print(f"\nDone! {count} courts seeded into the database.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
