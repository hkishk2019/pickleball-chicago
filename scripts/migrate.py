#!/usr/bin/env python3
"""Add new columns to an existing database without losing data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.database import engine


NEW_COLUMNS = [
    ("rating", "REAL"),
    ("review_count", "INTEGER"),
    ("booking_url", "VARCHAR"),
    ("booking_platform", "VARCHAR"),
    ("photo_url", "VARCHAR"),
    ("is_temporary", "BOOLEAN"),
    ("schedule_notes", "TEXT"),
]


def migrate():
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(courts)"))
        existing = {row[1] for row in result.fetchall()}

        added = 0
        for col_name, col_type in NEW_COLUMNS:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE courts ADD COLUMN {col_name} {col_type}"))
                added += 1
                print(f"  Added column: {col_name} ({col_type})")

        conn.commit()

    if added:
        print(f"\nMigration complete: {added} columns added.")
    else:
        print("No migration needed -- all columns already exist.")


if __name__ == "__main__":
    migrate()
