"""Chicago Pickleball Finder — Streamlit frontend.

Reads court data straight from the SQLite database (same one used by the
FastAPI backend).  If the DB is empty / missing it runs the seed pipeline.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st
from sqlalchemy import create_engine, func as sqlfunc
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.models import Base, Court

CHICAGO_LAT, CHICAGO_LNG = 41.8781, -87.6298
DB_PATH = ROOT / "pickleball.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
Session = sessionmaker(bind=engine)

PAGE_SIZE = 20

# ── Page config ──────────────────────────────────────────────────

st.set_page_config(
    page_title="Chicago Pickleball Finder",
    page_icon="🏓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="stSidebar"] {background: #f8faf8;}
    .court-card {border:1px solid #e5e7eb; border-radius:12px; padding:16px;
                 margin-bottom:8px; background:white;}
    .court-card:hover {border-color:#bbf7d0; box-shadow:0 4px 12px rgba(0,0,0,.06);}
    .badge {display:inline-block; padding:2px 10px; border-radius:8px;
            font-size:12px; font-weight:500; margin-right:4px; margin-bottom:4px;}
    .stars {color:#d97706;}
</style>
""", unsafe_allow_html=True)

# ── DB bootstrap ─────────────────────────────────────────────────

def _ensure_db():
    Base.metadata.create_all(bind=engine)
    with Session() as db:
        count = db.query(sqlfunc.count(Court.id)).scalar() or 0
    if count == 0:
        st.info("Database is empty — running seed + discovery pipeline (takes ~2–3 min on first deploy)…")
        from scripts.seed import main as seed_main
        seed_main()
        try:
            import asyncio
            from scripts.enrich import run_enrichment
            asyncio.run(run_enrichment())
        except Exception as exc:
            st.warning(f"Discovery enrichment had an error (seed data is still available): {exc}")
        st.rerun()


@st.cache_data(ttl=300)
def load_courts() -> pd.DataFrame:
    _ensure_db()
    with Session() as db:
        courts = db.query(Court).all()
        rows = [c.to_dict() for c in courts]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    return df

# ── Helpers ──────────────────────────────────────────────────────

def access_color(t):
    return {"public": "#15803d", "fee": "#c2410c", "members": "#4338ca"}.get(t, "#6b7280")

def access_bg(t):
    return {"public": "#f0fdf4", "fee": "#fff7ed", "members": "#eef2ff"}.get(t, "#f3f4f6")

def _rgb(t):
    """Return pydeck-friendly [R,G,B,A] for access type."""
    return {
        "public": [22, 101, 52, 200],
        "fee": [194, 65, 12, 200],
        "members": [67, 56, 202, 200],
    }.get(t, [107, 114, 128, 200])

# ── Sidebar filters ──────────────────────────────────────────────

df_all = load_courts()

st.sidebar.markdown("## 🏓 Chicago Pickleball")
st.sidebar.caption(f"{len(df_all)} locations loaded")

search = st.sidebar.text_input("Search courts, parks, addresses…", key="search")

st.sidebar.markdown("**Access type**")
col1, col2, col3 = st.sidebar.columns(3)
f_public = col1.checkbox("Public", key="f_public")
f_fee = col2.checkbox("Fee", key="f_fee")
f_members = col3.checkbox("Members", key="f_members")

st.sidebar.markdown("**Indoor / Outdoor**")
col4, col5 = st.sidebar.columns(2)
f_indoor = col4.checkbox("Indoor", key="f_indoor")
f_outdoor = col5.checkbox("Outdoor", key="f_outdoor")

sort_by = st.sidebar.selectbox("Sort by", ["Name", "Most courts", "Rating"], key="sort")

# ── Apply filters ────────────────────────────────────────────────

df = df_all.copy()

if search:
    q = search.lower()
    df = df[
        df["name"].str.lower().str.contains(q, na=False)
        | df["address"].str.lower().str.contains(q, na=False)
        | df["city"].str.lower().str.contains(q, na=False)
    ]

access_vals = []
if f_public:
    access_vals.append("public")
if f_fee:
    access_vals.append("fee")
if f_members:
    access_vals.append("members")
if access_vals:
    df = df[df["access_type"].isin(access_vals)]

if f_indoor and not f_outdoor:
    df = df[df["indoor_outdoor"].isin(["indoor", "both"])]
elif f_outdoor and not f_indoor:
    df = df[df["indoor_outdoor"].isin(["outdoor", "both"])]

if sort_by == "Most courts":
    df = df.sort_values("num_courts", ascending=False, na_position="last")
elif sort_by == "Rating":
    df = df.sort_values("rating", ascending=False, na_position="last")
else:
    df = df.sort_values("name", key=lambda s: s.str.lower(), na_position="last")

df = df.reset_index(drop=True)

# ── Stats bar ────────────────────────────────────────────────────

with Session() as db:
    total_courts_num = db.query(sqlfunc.sum(Court.num_courts)).scalar() or 0
    n_cities = db.query(sqlfunc.count(sqlfunc.distinct(Court.city))).scalar() or 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Locations", f"{len(df_all)}")
m2.metric("Shown", f"{len(df)}")
m3.metric("Total courts", f"{total_courts_num}")
m4.metric("Cities", f"{n_cities}")

# ── Layout: map + list ───────────────────────────────────────────

map_col, list_col = st.columns([3, 2])

# ── Map (pydeck — native, fast) ──────────────────────────────────

with map_col:
    map_df = df.dropna(subset=["latitude", "longitude"]).copy()

    if not map_df.empty:
        map_df["color"] = map_df["access_type"].apply(_rgb)
        map_df["radius"] = map_df["num_courts"].fillna(1).clip(lower=1).apply(lambda n: 40 + n * 15)
        map_df["tooltip_text"] = map_df.apply(
            lambda r: f"{r['name']}\n{r.get('address') or ''}"
                      + (f"\n★ {r['rating']}" if r.get("rating") else ""),
            axis=1,
        )

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["longitude", "latitude"],
            get_radius="radius",
            get_fill_color="color",
            pickable=True,
            auto_highlight=True,
            radius_min_pixels=6,
            radius_max_pixels=25,
        )

        view = pdk.ViewState(
            latitude=map_df["latitude"].mean(),
            longitude=map_df["longitude"].mean(),
            zoom=10,
            pitch=0,
        )

        st.pydeck_chart(
            pdk.Deck(
                layers=[layer],
                initial_view_state=view,
                tooltip={"text": "{tooltip_text}"},
                map_style="mapbox://styles/mapbox/light-v11",
            ),
            use_container_width=True,
            height=620,
        )
    else:
        st.info("No courts with coordinates to show on map.")

# ── Court list (paginated) ───────────────────────────────────────

with list_col:
    total_rows = len(df)
    if total_rows == 0:
        st.info("No courts match your filters.")
    else:
        total_pages = max(1, -(-total_rows // PAGE_SIZE))  # ceil division
        page = st.number_input(
            f"Page (1–{total_pages})", min_value=1, max_value=total_pages, value=1, key="page"
        )
        start = (page - 1) * PAGE_SIZE
        page_df = df.iloc[start : start + PAGE_SIZE]

        st.caption(f"Showing {start + 1}–{min(start + PAGE_SIZE, total_rows)} of {total_rows}")

        for _, row in page_df.iterrows():
            badges = ""
            if row.get("access_type"):
                bg, fg = access_bg(row["access_type"]), access_color(row["access_type"])
                badges += f'<span class="badge" style="background:{bg};color:{fg}">{row["access_type"].title()}</span>'
            if row.get("indoor_outdoor"):
                badges += f'<span class="badge" style="background:#eff6ff;color:#1d4ed8">{row["indoor_outdoor"].title()}</span>'
            if row.get("num_courts"):
                badges += f'<span class="badge" style="background:#f0fdf4;color:#166534">{int(row["num_courts"])} courts</span>'
            if row.get("booking_url"):
                badges += '<span class="badge" style="background:#f5f3ff;color:#7c3aed">Bookable</span>'
            if row.get("is_temporary"):
                badges += '<span class="badge" style="background:#fffbeb;color:#b45309">Shared court</span>'

            rating_html = ""
            if row.get("rating"):
                rating_html = f'<span class="stars">★ {row["rating"]}</span>'
                if row.get("review_count"):
                    rating_html += f' <span style="color:#9ca3af;font-size:12px">({int(row["review_count"])})</span>'

            addr = row.get("address") or ""
            city = row.get("city") or ""
            subtitle = f"{addr}, {city}" if addr and city else addr or city

            st.markdown(f"""<div class="court-card">
                <div style="display:flex;justify-content:space-between;align-items:start">
                    <b>{row['name']}</b> {rating_html}
                </div>
                <div style="font-size:13px;color:#6b7280;margin:4px 0 8px">{subtitle}</div>
                <div>{badges}</div>
            </div>""", unsafe_allow_html=True)

            with st.expander(f"Details: {row['name']}", expanded=False):
                if row.get("photo_url"):
                    st.image(row["photo_url"], use_container_width=True)

                dc1, dc2, dc3 = st.columns(3)
                dc1.metric("Courts", int(row["num_courts"]) if row.get("num_courts") else "—")
                dc2.metric("Access", (row.get("access_type") or "—").title())
                dc3.metric("Type", (row.get("indoor_outdoor") or "—").title())

                dc4, dc5, dc6 = st.columns(3)
                dc4.metric("Surface", (row.get("surface_type") or "—").title())
                dc5.metric("Nets", (row.get("net_type") or "—").title())
                dc6.metric("Lights", "Yes" if row.get("has_lights") else "No")

                if row.get("phone"):
                    st.markdown(f"📞 **Phone:** [{row['phone']}](tel:{row['phone']})")
                if row.get("hours"):
                    st.markdown(f"🕐 **Hours:** {row['hours']}")
                if row.get("price_info"):
                    st.markdown(f"💰 **Pricing:** {row['price_info']}")
                if row.get("schedule_notes"):
                    st.warning(row["schedule_notes"])
                if row.get("description"):
                    st.caption(row["description"])

                link_cols = st.columns(3)
                if row.get("booking_url"):
                    link_cols[0].link_button("Book Now", row["booking_url"])
                if row.get("latitude") and row.get("longitude"):
                    link_cols[1].link_button(
                        "Directions",
                        f"https://www.google.com/maps/dir/?api=1&destination={row['latitude']},{row['longitude']}",
                    )
                if row.get("website_url"):
                    link_cols[2].link_button("Website", row["website_url"])

                st.caption(
                    f"Source: {row.get('source', '—')}"
                    + (f" · Booking via {row['booking_platform']}" if row.get("booking_platform") else "")
                )
