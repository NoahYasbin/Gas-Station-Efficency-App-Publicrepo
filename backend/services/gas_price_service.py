"""
Gas station locations: OpenStreetMap Overpass API (free, no key required).
Prices: State-level EIA averages with brand adjustments and per-station noise.
Cache: 15 minutes, keyed by rounded lat/lng + fuel grade.
"""

import hashlib
import logging

import httpx

from cache import price_cache
from config import settings

log = logging.getLogger("gas_app.prices")

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# State average regular gas prices (USD/gal) — based on EIA weekly data
_STATE_PRICES: dict[str, float] = {
    "AL": 3.55, "AK": 4.65, "AZ": 4.10, "AR": 3.50, "CA": 5.30,
    "CO": 4.05, "CT": 4.35, "DE": 4.05, "FL": 3.85, "GA": 3.65,
    "HI": 5.40, "ID": 4.15, "IL": 4.25, "IN": 3.85, "IA": 3.75,
    "KS": 3.65, "KY": 3.70, "LA": 3.55, "ME": 4.25, "MD": 4.10,
    "MA": 4.35, "MI": 4.00, "MN": 3.90, "MS": 3.55, "MO": 3.65,
    "MT": 4.10, "NE": 3.75, "NV": 4.55, "NH": 4.20, "NJ": 4.15,
    "NM": 4.05, "NY": 4.35, "NC": 3.75, "ND": 3.75, "OH": 3.95,
    "OK": 3.55, "OR": 4.65, "PA": 4.25, "RI": 4.30, "SC": 3.60,
    "SD": 3.80, "TN": 3.65, "TX": 3.55, "UT": 4.25, "VT": 4.25,
    "VA": 3.95, "WA": 4.95, "WV": 3.85, "WI": 3.90, "WY": 4.00,
    "DC": 4.45,
}

_GRADE_ADDER: dict[str, float] = {
    "regular":  0.00,
    "midgrade": 0.40,
    "premium":  0.80,
    "diesel":   0.30,
    "e85":     -0.70,
}

# Brand premium/discount vs state average
_BRAND_DELTA: list[tuple[str, float]] = [
    ("costco",     -0.25),
    ("sam's club", -0.20),
    ("sams club",  -0.20),
    ("arco",       -0.12),
    ("ampm",       -0.12),
    ("raceway",    -0.08),
    ("circle k",   -0.04),
    ("speedway",   -0.04),
    ("sunoco",     -0.02),
    ("texaco",      0.02),
    ("76",          0.03),
    ("bp",          0.04),
    ("shell",       0.06),
    ("chevron",     0.07),
    ("exxon",       0.07),
    ("mobil",       0.07),
]


def _price(name: str, state: str, fuel_grade: str) -> float:
    base = _STATE_PRICES.get(state.upper(), 3.40) + _GRADE_ADDER.get(fuel_grade, 0.0)

    delta = 0.0
    name_lower = name.lower()
    for brand, adj in _BRAND_DELTA:
        if brand in name_lower:
            delta = adj
            break

    # Deterministic ±4 cents per station (consistent across requests)
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    noise = (h % 9 - 4) * 0.01

    return round(max(2.20, base + delta + noise), 3)


def _parse_element(el: dict, state: str, fuel_grade: str) -> dict | None:
    tags = el.get("tags", {})

    if el["type"] == "way":
        center = el.get("center", {})
        lat, lng = center.get("lat"), center.get("lon")
    else:
        lat, lng = el.get("lat"), el.get("lon")

    if lat is None or lng is None:
        return None

    name = tags.get("name") or tags.get("brand") or "Gas Station"

    house  = (tags.get("addr:housenumber", "") + " " + tags.get("addr:street", "")).strip()
    city   = tags.get("addr:city", "")
    addr_s = tags.get("addr:state", "")
    address = ", ".join(p for p in [house, city, addr_s] if p)

    return {
        "name":             name,
        "address":          address,
        "lat":              float(lat),
        "lng":              float(lng),
        "price_per_gallon": _price(name, state, fuel_grade),
    }


async def get_stations_with_prices(
    lat: float,
    lng: float,
    state: str,
    fuel_grade: str = "regular",
    radius_miles: float = 5.0,
) -> list[dict]:
    cache_key = f"{lat:.2f}:{lng:.2f}:{fuel_grade}"
    cached = price_cache.get(cache_key)
    if cached is not None:
        log.info("Cache hit for %s", cache_key)
        return cached

    radius_m = int(radius_miles * 1609)
    query = (
        f'[out:json][timeout:25];'
        f'(node["amenity"="fuel"](around:{radius_m},{lat},{lng});'
        f'way["amenity"="fuel"](around:{radius_m},{lat},{lng}););'
        f'out center 30;'
    )

    log.info("Querying Overpass: lat=%.4f lng=%.4f radius=%dm", lat, lng, radius_m)
    body = None
    async with httpx.AsyncClient() as client:
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                response = await client.post(
                    endpoint,
                    data={"data": query},
                    headers={"User-Agent": "GasApp/1.0"},
                    timeout=40.0,
                )
                log.info("Overpass HTTP %s from %s", response.status_code, endpoint)
                if response.is_success:
                    body = response.json()
                    break
                log.warning("Overpass endpoint %s returned %s", endpoint, response.status_code)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                log.warning("Overpass endpoint %s failed: %s — trying next", endpoint, e)

    if body is None:
        raise ValueError("All Overpass endpoints timed out. Try again in a moment.")

    elements = body.get("elements", [])
    log.info("Overpass returned %d elements", len(elements))

    stations = [s for el in elements if (s := _parse_element(el, state, fuel_grade)) is not None]

    # Deduplicate by name + rounded coords
    seen: set[tuple] = set()
    unique: list[dict] = []
    for s in stations:
        key = (s["name"], round(s["lat"], 3), round(s["lng"], 3))
        if key not in seen:
            seen.add(key)
            unique.append(s)

    log.info("%d unique stations after dedup", len(unique))
    price_cache.set(cache_key, unique, ttl=settings.price_cache_ttl_seconds)
    return unique
