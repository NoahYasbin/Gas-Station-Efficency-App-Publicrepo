import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from fastapi import APIRouter, HTTPException, Request

from ..schemas import RecommendRequest, RecommendResponse, StationOut
from ..services.gas_price_service import get_stations_with_prices
from ..services.routing_service import (
    get_location_from_ip,
    reverse_geocode,
    get_driving_distances,
)
from costcalc import (
    VehicleParams,
    Station,
    recommend,
    InvalidParamsError,
    UnreachableStationError,
)

router = APIRouter()
log = logging.getLogger("gas_app.recommend")


def _to_station_out(result, meta: dict) -> StationOut:
    return StationOut(
        name=result.station.name,
        address=meta.get("address", ""),
        latitude=meta["lat"],
        longitude=meta["lng"],
        price_per_gallon=result.station.price_per_gallon,
        distance_miles=result.station.distance_miles,
        drive_time_minutes=result.station.drive_time_minutes,
        effective_cost=result.effective_cost,
        gallons_purchased=result.gallons_purchased,
        fuel_burned_in_transit=result.fuel_burned_in_transit,
        rank=result.rank,
        savings_vs_best=result.savings_vs_best,
        reachable=result.reachable,
    )


def _client_ip(request: Request) -> str:
    """
    Read client IP only to pass to ip-api for location resolution.
    Never logged, stored, or included in any response — discarded
    immediately after ip-api returns a ZIP code.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


@router.post("/recommend", response_model=RecommendResponse)
async def get_recommendation(body: RecommendRequest, request: Request):
    # 1. Validate vehicle params early — fail fast before any API calls
    try:
        vehicle = VehicleParams(
            mpg=body.vehicle.mpg,
            tank_current=body.vehicle.tank_current,
            tank_capacity=body.vehicle.tank_capacity,
        )
    except InvalidParamsError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 2. Resolve location
    try:
        if body.latitude is not None and body.longitude is not None:
            log.info("GPS path: lat=%.4f lng=%.4f", body.latitude, body.longitude)
            geo = await reverse_geocode(body.latitude, body.longitude)
        else:
            ip = _client_ip(request)
            log.info("IP path: resolving location from client IP")
            geo = await get_location_from_ip(ip)
        log.info("Location resolved: zip=%s city=%s state=%s", geo["zip"], geo.get("city"), geo["state"])
    except Exception as e:
        log.error("Location step failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    lat, lng = geo["lat"], geo["lng"]

    # 3. Fetch station locations + prices via Overpass (OpenStreetMap)
    try:
        price_stations = await get_stations_with_prices(
            lat, lng, geo["state"], body.fuel_grade, body.search_radius_miles
        )
    except Exception as e:
        log.error("Overpass step failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    if not price_stations:
        log.warning("No stations returned near %.4f, %.4f", lat, lng)
        raise HTTPException(
            status_code=404,
            detail="No gas stations found nearby. Try increasing the search radius.",
        )

    # 4. Real road distances (OSRM)
    try:
        stations_with_distances = await get_driving_distances(lat, lng, price_stations)
    except Exception as e:
        log.error("OSRM step failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    if not stations_with_distances:
        raise HTTPException(
            status_code=404,
            detail="Could not calculate a route to any nearby stations.",
        )

    log.info("Pipeline complete: %d stations ranked", len(stations_with_distances))

    # 5. Build Station objects; track metadata by object id to avoid name collisions
    stations: list[Station] = []
    meta_map: dict[int, dict] = {}

    for s in stations_with_distances:
        station = Station(
            name=s["name"],
            price_per_gallon=s["price_per_gallon"],
            distance_miles=s["distance_miles"],
            drive_time_minutes=s["drive_time_minutes"],
        )
        stations.append(station)
        meta_map[id(station)] = s

    # 6. Run cost engine
    try:
        rec = recommend(stations, vehicle)
    except UnreachableStationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    region_avg = sum(s["price_per_gallon"] for s in stations_with_distances) / len(
        stations_with_distances
    )

    return RecommendResponse(
        best_station=_to_station_out(rec.best_station, meta_map[id(rec.best_station.station)]),
        all_stations=[
            _to_station_out(r, meta_map[id(r.station)]) for r in rec.all_results
        ],
        note=rec.note,
        region_avg_price=round(region_avg, 3),
        city=geo.get("city", ""),
        state=geo["state"],
        tank_is_full=rec.tank_is_full,
    )
