"""
Location and routing services.

ip-api.com (free tier)
  IP → location (lat/lon, ZIP, city, state)
  URL: http://ip-api.com/json/{ip}   — HTTP only on free tier; 45 req/min
  No API key needed.

Nominatim (OpenStreetMap)
  lat/lon → ZIP + state (used when the caller provides GPS coordinates)
  URL: https://nominatim.openstreetmap.org/reverse
  Requires User-Agent header; max 1 req/sec per usage policy.

OSRM (Open Source Routing Machine)
  Driving distance matrix: one origin → many destinations
  URL: https://router.project-osrm.org/table/v1/driving/
  Coordinates are lon,lat order (reversed from lat,lon convention).
"""

import logging

import httpx

log = logging.getLogger("gas_app.routing")

NOMINATIM_HEADERS = {"User-Agent": "GasEfficiencyApp/0.3 (portfolio project)"}
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

IP_API_URL = "http://ip-api.com/json"
IP_API_FIELDS = "status,message,lat,lon,city,regionName,region,zip,query"

OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving"
OSRM_BATCH_SIZE = 50


async def get_location_from_ip(ip_address: str) -> dict:
    """
    Resolve an IP address to geographic location via ip-api.com (free tier).

    Returns {"lat": float, "lng": float, "zip": str, "city": str, "state": str}.

    ip-api free tier is HTTP-only and limited to 45 req/min. Loopback/private
    addresses (127.x, 192.168.x, etc.) are not routable — ip-api returns an
    error and we raise ValueError with an actionable message.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{IP_API_URL}/{ip_address}",
            params={"fields": IP_API_FIELDS},
            timeout=10.0,
        )
        response.raise_for_status()

    data = response.json()

    if data.get("status") != "success":
        msg = data.get("message", "unknown error")
        raise ValueError(
            f"ip-api could not resolve '{ip_address}': {msg}. "
            "If running locally, pass latitude/longitude in the request body instead."
        )

    zip_code = data.get("zip", "")
    state = data.get("region", "")  # 2-letter abbreviation (e.g. "DE")
    city = data.get("city", "")

    if not zip_code:
        raise ValueError(
            f"ip-api resolved '{ip_address}' to {city} but returned no ZIP code. "
            "Pass latitude/longitude in the request body to override IP-based location."
        )

    return {
        "lat": float(data["lat"]),
        "lng": float(data["lon"]),
        "zip": zip_code,
        "city": city,
        "state": state,
    }


async def reverse_geocode(lat: float, lng: float) -> dict:
    """
    lat/lon → {"lat", "lng", "zip", "city", "state"} via Nominatim.

    Used when the client provides GPS coordinates so we can derive the ZIP
    needed for GasBuddy's location search.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            NOMINATIM_REVERSE_URL,
            headers=NOMINATIM_HEADERS,
            params={"lat": lat, "lon": lng, "format": "json"},
            timeout=10.0,
        )
        response.raise_for_status()

    data = response.json()
    address = data.get("address", {})

    zip_code = address.get("postcode")
    iso = address.get("ISO3166-2-lvl4", "")  # e.g. "US-CA"
    state = iso.split("-")[1] if "-" in iso else None
    city = address.get("city") or address.get("town") or address.get("village", "")

    if not zip_code:
        raise ValueError(
            "Could not determine ZIP code from your coordinates. "
            "Make sure the location is within the United States."
        )
    if not state:
        raise ValueError(
            "Could not determine state from your coordinates. "
            "Make sure the location is within the United States."
        )

    return {"lat": lat, "lng": lng, "zip": zip_code, "city": city, "state": state}


async def get_driving_distances(
    origin_lat: float,
    origin_lng: float,
    stations: list[dict],
) -> list[dict]:
    """
    Enriches each station dict with 'distance_miles' and 'drive_time_minutes'
    using the OSRM Table API. Processes in batches of OSRM_BATCH_SIZE.

    OSRM coordinates are lon,lat order (reversed from lat,lon convention).
    Stations with no drivable route (null returned by OSRM) are dropped.
    Returns a new list — does not mutate the input dicts.
    """
    enriched = []

    async with httpx.AsyncClient() as client:
        for i in range(0, len(stations), OSRM_BATCH_SIZE):
            batch = stations[i : i + OSRM_BATCH_SIZE]

            coords = ";".join(
                [f"{origin_lng},{origin_lat}"]
                + [f"{s['lng']},{s['lat']}" for s in batch]
            )

            response = await client.get(
                f"{OSRM_TABLE_URL}/{coords}",
                params={"sources": "0", "annotations": "distance,duration"},
                timeout=15.0,
            )
            response.raise_for_status()

            data = response.json()
            if data.get("code") != "Ok":
                raise ValueError(
                    f"OSRM routing error: {data.get('code')} — {data.get('message', 'no detail')}. "
                    "The public OSRM server may be temporarily overloaded; try again shortly."
                )

            durations = data["durations"][0]
            distances = data["distances"][0]

            for j, station in enumerate(batch):
                dist_m = distances[j + 1]
                dur_s = durations[j + 1]

                if dist_m is None or dur_s is None:
                    continue

                enriched.append({
                    **station,
                    "distance_miles": dist_m / 1609.344,
                    "drive_time_minutes": dur_s / 60,
                })

    return enriched
