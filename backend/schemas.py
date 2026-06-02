from typing import Optional
from pydantic import BaseModel, Field


class VehicleInput(BaseModel):
    mpg: float = Field(..., gt=0, description="Miles per gallon")
    tank_current: float = Field(..., ge=0, description="Gallons currently in tank")
    tank_capacity: float = Field(..., gt=0, description="Total tank capacity in gallons")


class RecommendRequest(BaseModel):
    # lat/lon are optional — if omitted the backend detects location from the client IP
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    vehicle: VehicleInput
    search_radius_miles: float = Field(default=5.0, gt=0, le=25)
    fuel_grade: str = Field(
        default="regular",
        pattern="^(regular|midgrade|premium|diesel|e85)$",
    )


class StationOut(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float
    price_per_gallon: float
    distance_miles: float
    drive_time_minutes: Optional[float]
    effective_cost: float
    gallons_purchased: float
    fuel_burned_in_transit: float
    rank: int
    savings_vs_best: float
    reachable: bool


class RecommendResponse(BaseModel):
    best_station: StationOut
    all_stations: list[StationOut]
    note: str
    region_avg_price: float
    city: str
    state: str
    tank_is_full: bool
