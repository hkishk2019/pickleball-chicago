/* Chicago Pickleball Finder – Frontend Logic */

const API = window.location.origin + "/api";
const CHICAGO = { lat: 41.8781, lng: -87.6298 };

let map, mobileMap, markerGroup, mobileMarkerGroup;
let allCourts = [];
let activeFilters = {};
let userLocation = null;

// ── Initialization ──────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  loadStats();
  loadCourts();
  bindEvents();
});

function initMap() {
  map = L.map("map", { zoomControl: false }).setView([CHICAGO.lat, CHICAGO.lng], 11);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 19,
  }).addTo(map);
  markerGroup = L.layerGroup().addTo(map);
}

function initMobileMap() {
  if (mobileMap) return;
  mobileMap = L.map("mobile-map", { zoomControl: false }).setView([CHICAGO.lat, CHICAGO.lng], 11);
  L.control.zoom({ position: "bottomright" }).addTo(mobileMap);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OSM &copy; CARTO',
    maxZoom: 19,
  }).addTo(mobileMap);
  mobileMarkerGroup = L.layerGroup().addTo(mobileMap);
}

// ── Data Loading ────────────────────────────────────────────────

async function loadStats() {
  try {
    const resp = await fetch(`${API}/stats`);
    const stats = await resp.json();
    const badge = document.getElementById("stats-badge");
    badge.textContent = `${stats.total_locations} locations · ${stats.total_courts} courts · ${stats.cities} cities`;
    badge.classList.remove("hidden");
  } catch (e) { /* ignore */ }
}

async function loadCourts(params = {}) {
  const list = document.getElementById("court-list");
  const loading = document.getElementById("loading-indicator");
  const empty = document.getElementById("empty-state");

  loading.classList.remove("hidden");
  empty.classList.add("hidden");
  list.innerHTML = "";

  const url = new URL(`${API}/courts`);
  url.searchParams.set("limit", "500");
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  }

  try {
    const resp = await fetch(url);
    const data = await resp.json();
    allCourts = data.courts || [];
  } catch (e) {
    allCourts = [];
  }

  loading.classList.add("hidden");
  renderCourts(allCourts);
  renderMarkers(allCourts);
  updateResultsCount(allCourts.length);
}

// ── Rendering ───────────────────────────────────────────────────

function renderCourts(courts) {
  const list = document.getElementById("court-list");
  const empty = document.getElementById("empty-state");

  if (!courts.length) {
    list.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  list.innerHTML = courts.map((c) => `
    <div class="court-card bg-white border border-gray-100 rounded-xl p-4 cursor-pointer hover:border-pickle-200"
         data-id="${c.id}" onclick="showDetail(${c.id})">
      <div class="flex items-start justify-between gap-2 mb-1.5">
        <h3 class="font-semibold text-sm leading-snug">${esc(c.name)}</h3>
        <div class="flex items-center gap-1.5 shrink-0">
          ${c.rating ? `<span class="flex items-center gap-0.5 text-xs font-semibold text-amber-600"><svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>${c.rating}</span>` : ""}
          ${c.num_courts ? `<span class="text-xs font-bold text-pickle-700 bg-pickle-50 px-2 py-0.5 rounded-full">${c.num_courts} ct</span>` : ""}
        </div>
      </div>
      <p class="text-xs text-gray-500 mb-2">${esc(c.address || "")}${c.city ? ", " + esc(c.city) : ""}</p>
      <div class="flex flex-wrap gap-1.5">
        ${badge(c.access_type, accessColor(c.access_type))}
        ${badge(c.indoor_outdoor, "bg-blue-50 text-blue-700")}
        ${c.price_info ? badge(c.price_info, "bg-emerald-50 text-emerald-700") : ""}
        ${c.is_temporary ? badge("Shared court", "bg-amber-50 text-amber-700") : ""}
        ${c.surface_type ? badge(c.surface_type, "bg-gray-100 text-gray-600") : ""}
        ${c.has_lights ? badge("lights", "bg-yellow-50 text-yellow-700") : ""}
        ${c.booking_url ? badge("Bookable", "bg-violet-50 text-violet-700") : ""}
        ${c.distance_m != null ? badge(formatDist(c.distance_m), "bg-purple-50 text-purple-700") : ""}
      </div>
    </div>
  `).join("");
}

function renderMarkers(courts) {
  markerGroup.clearLayers();
  if (mobileMarkerGroup) mobileMarkerGroup.clearLayers();

  const bounds = [];
  for (const c of courts) {
    if (!c.latitude || !c.longitude) continue;
    bounds.push([c.latitude, c.longitude]);

    const icon = L.divIcon({
      className: "",
      html: `<div style="width:28px;height:28px;background:#166534;border:2.5px solid white;border-radius:50%;box-shadow:0 2px 6px rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;">
        <span style="color:white;font-size:11px;font-weight:700;font-family:Inter,sans-serif">${c.num_courts || ""}</span>
      </div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });

    const popup = `
      <div style="padding:12px 14px;font-family:Inter,sans-serif">
        <div style="font-weight:700;font-size:14px;margin-bottom:4px">${esc(c.name)}</div>
        <div style="font-size:12px;color:#6b7280;margin-bottom:8px">${esc(c.address || "")}${c.city ? ", " + esc(c.city) : ""}</div>
        ${c.phone ? `<a href="tel:${c.phone.replace(/\D/g, "")}" style="font-size:12px;color:#16a34a;text-decoration:none">${esc(c.phone)}</a><br>` : ""}
        <a href="#" onclick="event.preventDefault();showDetail(${c.id})" style="font-size:12px;color:#16a34a;font-weight:600;text-decoration:none;margin-top:4px;display:inline-block">View details &rarr;</a>
      </div>`;

    const marker = L.marker([c.latitude, c.longitude], { icon }).bindPopup(popup);
    markerGroup.addLayer(marker);
    if (mobileMarkerGroup) {
      const m2 = L.marker([c.latitude, c.longitude], { icon: L.divIcon(icon.options) }).bindPopup(popup);
      mobileMarkerGroup.addLayer(m2);
    }
  }

  if (bounds.length) {
    map.fitBounds(bounds, { padding: [30, 30] });
    if (mobileMap) mobileMap.fitBounds(bounds, { padding: [30, 30] });
  }
}

function updateResultsCount(n) {
  document.getElementById("results-count").textContent = `${n} court${n !== 1 ? "s" : ""} found`;
}

// ── Detail Modal ────────────────────────────────────────────────

async function showDetail(id) {
  const modal = document.getElementById("detail-modal");
  const nameEl = document.getElementById("detail-name");
  const body = document.getElementById("detail-body");

  const court = allCourts.find((c) => c.id === id);
  if (!court) return;

  nameEl.textContent = court.name;

  const directionsUrl = court.latitude && court.longitude
    ? `https://www.google.com/maps/dir/?api=1&destination=${court.latitude},${court.longitude}`
    : court.address
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(court.address + " " + (court.city || ""))}`
    : null;

  const ratingHtml = court.rating ? `
    <div class="flex items-center gap-2 mb-3">
      <div class="flex items-center gap-1">${stars(court.rating)}</div>
      <span class="text-sm font-semibold text-gray-700">${court.rating}</span>
      ${court.review_count ? `<span class="text-xs text-gray-400">(${court.review_count} reviews)</span>` : ""}
    </div>` : "";

  const photoHtml = court.photo_url ? `
    <div class="rounded-xl overflow-hidden h-40 mb-3 bg-gray-100">
      <img src="${esc(court.photo_url)}" alt="${esc(court.name)}" class="w-full h-full object-cover" loading="lazy" onerror="this.parentElement.style.display='none'" />
    </div>` : "";

  body.innerHTML = `
    ${photoHtml}
    ${ratingHtml}

    <div class="space-y-3">
      ${court.address ? `
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-gray-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 0115 0z"/></svg>
        <div>
          <p class="text-sm font-medium">${esc(court.address)}</p>
          <p class="text-xs text-gray-500">${[court.city, court.zip_code].filter(Boolean).join(", ")}</p>
        </div>
      </div>` : ""}

      ${court.phone ? `
      <div class="flex items-center gap-3">
        <svg class="w-5 h-5 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z"/></svg>
        <a href="tel:${court.phone.replace(/\D/g, "")}" class="text-sm font-medium text-pickle-600 hover:underline">${esc(court.phone)}</a>
      </div>` : ""}
    </div>

    <div class="grid grid-cols-2 gap-3">
      ${statCard("Courts", court.num_courts || "—")}
      ${statCard("Access", capitalize(court.access_type) || "—")}
      ${statCard("Type", capitalize(court.indoor_outdoor) || "—")}
      ${statCard("Surface", capitalize(court.surface_type) || "—")}
      ${statCard("Nets", capitalize(court.net_type) || "—")}
      ${statCard("Lights", court.has_lights ? "Yes" : "No")}
    </div>

    ${court.hours ? `<div class="bg-gray-50 rounded-lg p-3"><p class="text-xs font-medium text-gray-500 mb-1">Hours</p><p class="text-sm">${esc(court.hours)}</p></div>` : ""}
    ${court.price_info ? `<div class="bg-gray-50 rounded-lg p-3"><p class="text-xs font-medium text-gray-500 mb-1">Pricing</p><p class="text-sm">${esc(court.price_info)}</p></div>` : ""}
    ${court.schedule_notes ? `<div class="bg-amber-50 border border-amber-100 rounded-lg p-3"><p class="text-xs font-medium text-amber-600 mb-1">${court.is_temporary ? "Shared / Converted Court" : "Schedule Notes"}</p><p class="text-sm text-amber-800">${esc(court.schedule_notes)}</p></div>` : ""}
    ${court.description ? `<div class="bg-gray-50 rounded-lg p-3"><p class="text-xs font-medium text-gray-500 mb-1">Details</p><p class="text-sm text-gray-700">${esc(court.description)}</p></div>` : ""}

    <div class="flex gap-2 pt-2">
      ${court.booking_url ? `<a href="${esc(court.booking_url)}" target="_blank" rel="noopener" class="flex-1 flex items-center justify-center gap-2 py-2.5 bg-violet-600 text-white text-sm font-semibold rounded-xl hover:bg-violet-700 transition">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"/></svg>
        Book Now
      </a>` : ""}
      ${directionsUrl ? `<a href="${directionsUrl}" target="_blank" rel="noopener" class="flex-1 flex items-center justify-center gap-2 py-2.5 bg-pickle-600 text-white text-sm font-semibold rounded-xl hover:bg-pickle-700 transition">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l5.447 2.724A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/></svg>
        Directions
      </a>` : ""}
      ${court.website_url ? `<a href="${court.website_url}" target="_blank" rel="noopener" class="flex-1 flex items-center justify-center gap-2 py-2.5 border border-gray-200 text-sm font-semibold rounded-xl hover:bg-gray-50 transition">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"/></svg>
        Website
      </a>` : ""}
    </div>

    <p class="text-[10px] text-gray-400 text-center">Data sourced from ${esc(court.source || "multiple sources")}${court.booking_platform ? " · Booking via " + esc(court.booking_platform) : ""} · Last updated ${court.last_updated ? new Date(court.last_updated).toLocaleDateString() : "—"}</p>
  `;

  modal.classList.remove("hidden");
}

function closeDetail() {
  document.getElementById("detail-modal").classList.add("hidden");
}

// ── Events ──────────────────────────────────────────────────────

function bindEvents() {
  let searchTimeout;
  document.getElementById("search-input").addEventListener("input", (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      activeFilters.q = e.target.value.trim();
      fetchWithFilters();
    }, 300);
  });

  document.querySelectorAll(".filter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const filter = chip.dataset.filter;
      const value = chip.dataset.value;

      if (chip.classList.contains("active")) {
        chip.classList.remove("active");
        delete activeFilters[filter];
      } else {
        document.querySelectorAll(`.filter-chip[data-filter="${filter}"]`).forEach(
          (c) => c.classList.remove("active")
        );
        chip.classList.add("active");
        activeFilters[filter] = value;
      }
      fetchWithFilters();
    });
  });

  document.getElementById("locate-btn").addEventListener("click", geolocate);

  document.getElementById("toggle-map-btn").addEventListener("click", () => {
    const overlay = document.getElementById("mobile-map-overlay");
    overlay.classList.remove("hidden");
    initMobileMap();
    setTimeout(() => {
      mobileMap.invalidateSize();
      renderMarkers(allCourts);
    }, 100);
  });

  document.getElementById("close-mobile-map").addEventListener("click", () => {
    document.getElementById("mobile-map-overlay").classList.add("hidden");
  });

  document.getElementById("modal-backdrop").addEventListener("click", closeDetail);
  document.getElementById("modal-close").addEventListener("click", closeDetail);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDetail();
  });
}

function fetchWithFilters() {
  const params = { ...activeFilters };
  if (userLocation) {
    params.lat = userLocation.lat;
    params.lng = userLocation.lng;
    if (!params.sort) params.sort = "distance";
  }
  loadCourts(params);
}

function geolocate() {
  if (!navigator.geolocation) return alert("Geolocation is not supported by your browser");

  const btn = document.getElementById("locate-btn");
  btn.disabled = true;
  btn.innerHTML = `<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>`;

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      btn.disabled = false;
      btn.innerHTML = `<svg class="w-4 h-4 text-pickle-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4m10-10h-4M6 12H2"/><circle cx="12" cy="12" r="4"/></svg><span class="hidden sm:inline">Near me</span>`;
      activeFilters.sort = "distance";
      fetchWithFilters();
    },
    (err) => {
      btn.disabled = false;
      btn.innerHTML = `<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4m10-10h-4M6 12H2"/><circle cx="12" cy="12" r="4"/></svg><span class="hidden sm:inline">Near me</span>`;
      alert("Could not get your location. Please allow location access.");
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

// ── Helpers ──────────────────────────────────────────────────────

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function capitalize(s) {
  if (!s) return "";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function badge(text, classes) {
  if (!text) return "";
  return `<span class="inline-block px-2 py-0.5 rounded-md text-[11px] font-medium ${classes}">${capitalize(text)}</span>`;
}

function accessColor(type) {
  if (type === "public") return "bg-green-50 text-green-700";
  if (type === "fee") return "bg-orange-50 text-orange-700";
  if (type === "members") return "bg-indigo-50 text-indigo-700";
  if (type === "private") return "bg-red-50 text-red-700";
  return "bg-gray-100 text-gray-600";
}

function formatDist(meters) {
  const mi = meters / 1609.34;
  return mi < 0.1 ? `${Math.round(meters)}m` : `${mi.toFixed(1)} mi`;
}

function stars(rating) {
  let html = "";
  const full = Math.floor(rating);
  const half = rating - full >= 0.3;
  for (let i = 0; i < 5; i++) {
    if (i < full) {
      html += `<svg class="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>`;
    } else if (i === full && half) {
      html += `<svg class="w-4 h-4 text-amber-400" viewBox="0 0 20 20"><defs><linearGradient id="hg"><stop offset="50%" stop-color="currentColor"/><stop offset="50%" stop-color="#d1d5db"/></linearGradient></defs><path fill="url(#hg)" d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>`;
    } else {
      html += `<svg class="w-4 h-4 text-gray-300" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>`;
    }
  }
  return html;
}

function statCard(label, value) {
  return `<div class="bg-gray-50 rounded-lg p-3 text-center">
    <p class="text-xs text-gray-500 mb-0.5">${label}</p>
    <p class="text-sm font-semibold">${value}</p>
  </div>`;
}

window.showDetail = showDetail;
