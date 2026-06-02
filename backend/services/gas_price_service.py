"""
Gas station locations: OpenStreetMap Overpass API (free, no key required).
Prices: State-level EIA averages with brand adjustments and per-station noise.
Cache: 15 minutes, keyed by rounded lat/lng + fuel grade.
"""

import hashlib
import logging

import httpx

from ..cache import price_cache
from ..config import settings

log = logging.getLogger("gas_app.prices")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# State average regular gas prices (USD/gal) — based on EIA weekly data
_STATE_PRICES: dict[str, float] = {
    "AL": 3.05, "AK": 4.15, "AZ": 3.60, "AR": 3.00, "CA": 4.80,
    "CO": 3.55, "CT": 3.85, "DE": 3.55, "FL": 3.35, "GA": 3.15,
    "HI": 4.90, "ID": 3.65, "IL": 3.75, "IN": 3.35, "IA": 3.25,
    "KS": 3.15, "KY": 3.20, "LA": 3.05, "ME": 3.75, "MD": 3.60,
    "MA": 3.85, "MI": 3.50, "MN": 3.40, "MS": 3.05, "MO": 3.15,
    "MT": 3.60, "NE": 3.25, "NV": 4.05, "NH": 3.70, "NJ": 3.65,
    "NM": 3.55, "NY": 3.85, "NC": 3.25, "ND": 3.25, "OH": 3.45,
    "OK": 3.05, "OR": 4.15, "PA": 3.75, "RI": 3.80, "SC": 3.10,
    "SD": 3.30, "TN": 3.15, "TX": 3.05, "UT": 3.75, "VT": 3.75,
    "VA": 3.45, "WA": 4.45, "WV": 3.35, "WI": 3.40, "WY": 3.50,
    "DC": 3.95,
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
        f'[out:json][timeout:15];'
        f'(node["amenity"="fuel"](around:{radius_m},{lat},{lng});'
        f'way["amenity"="fuel"](around:{radius_m},{lat},{lng}););'
        f'out center 30;'
    )

    log.info("Querying Overpass: lat=%.4f lng=%.4f radius=%dm", lat, lng, radius_m)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "GasApp/1.0"},
            timeout=25.0,
        )
        log.info("Overpass HTTP %s", response.status_code)
        if not response.is_success:
            log.error("Overpass error: %s", response.text[:300])
        response.raise_for_status()
        body = response.json()

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
