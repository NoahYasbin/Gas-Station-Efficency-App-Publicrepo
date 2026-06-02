"""
costcalc.py — Core cost calculation engine for the Gas Efficiency App.

The key insight: the cheapest gas station per gallon is not always the most
cost-efficient choice once driving distance and fuel consumption are considered.

Math model:

If you drive d miles to a station priced at p $/gal with efficiency mpg:

    transit_fuel  = d / mpg
    gallons_bought = gallons_to_fill + transit_fuel
    effective_cost = gallons_bought * p

Farther stations require you to replace the fuel burned getting there, so you
buy more gallons at that price. This makes cross-station comparison fair.

Why this works:

Suppose two stations A and B. You need to fill your tank regardless; the only
question is where. The extra gallons you purchase at a far station to replace
your transit fuel are priced at that station's rate — so a farther cheaper
station isn't always cheaper in total.

Savings from choosing B over A:
    savings = effective_cost_A - effective_cost_B
    (positive = B is better; negative = A is better)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CostCalcError(Exception):
    """Base error for cost calculation failures."""


class InvalidParamsError(CostCalcError):
    """Raised when input parameters are out of valid range."""


class UnreachableStationError(CostCalcError):
    """Raised when no stations can be reached with current fuel level."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class VehicleParams:
    """Immutable snapshot of vehicle state used for one calculation run."""

    mpg: float           # miles per gallon (city/highway mix)
    tank_current: float  # gallons currently in tank
    tank_capacity: float # total tank capacity in gallons

    def __post_init__(self) -> None:
        if self.mpg <= 0:
            raise InvalidParamsError(f"MPG must be positive, got {self.mpg}")
        if self.tank_capacity <= 0:
            raise InvalidParamsError(f"Tank capacity must be positive, got {self.tank_capacity}")
        if self.tank_current < 0:
            raise InvalidParamsError(f"Current fuel cannot be negative, got {self.tank_current}")
        if self.tank_current > self.tank_capacity:
            raise InvalidParamsError(
                f"Current fuel ({self.tank_current} gal) exceeds "
                f"tank capacity ({self.tank_capacity} gal)"
            )

    @property
    def gallons_to_fill(self) -> float:
        """Gallons needed to reach a full tank."""
        return self.tank_capacity - self.tank_current

    @property
    def range_remaining(self) -> float:
        """Miles the vehicle can travel before running out of fuel."""
        return self.tank_current * self.mpg


@dataclass
class Station:
    """A candidate gas station with real road distance from the user's location."""

    name: str
    price_per_gallon: float   # USD, regular unleaded
    distance_miles: float     # real road distance (not straight-line)
    drive_time_minutes: Optional[float] = None  # populated by routing API

    def __post_init__(self) -> None:
        if self.price_per_gallon <= 0:
            raise InvalidParamsError(
                f"Price must be positive for '{self.name}', got {self.price_per_gallon}"
            )
        if self.distance_miles < 0:
            raise InvalidParamsError(
                f"Distance cannot be negative for '{self.name}', got {self.distance_miles}"
            )
        if self.drive_time_minutes is not None and self.drive_time_minutes < 0:
            raise InvalidParamsError(f"Drive time cannot be negative for '{self.name}'")


@dataclass
class StationResult:
    """Computed cost outcome for a single station."""

    station: Station
    effective_cost: float          # total USD: fill-up cost including transit fuel replacement
    gallons_purchased: float       # gallons bought at this station (g_fill + transit fuel)
    fuel_burned_in_transit: float  # gallons consumed driving to this station
    reachable: bool                # False when current fuel < fuel needed to arrive
    rank: int = 0                  # 1 = best effective cost; unreachable stations ranked last
    savings_vs_best: float = 0.0   # USD saved vs the rank-1 station; ≤ 0 for all but rank-1

    @property
    def effective_price_per_gallon(self) -> float:
        """
        All-in cost per gallon including transit fuel.
        Comparable across stations regardless of distance.
        """
        if self.gallons_purchased == 0:
            return float("inf")
        return self.effective_cost / self.gallons_purchased


@dataclass
class Recommendation:
    """Output of the top-level recommend() function."""

    best_station: StationResult
    all_results: list[StationResult]  # ordered best → worst; unreachable at the end
    vehicle: VehicleParams
    tank_is_full: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def calculate_station_result(station: Station, vehicle: VehicleParams) -> StationResult:
    """
    Compute the effective cost of filling up at one station.

    Effective cost = (gallons_to_fill + transit_fuel) * station_price

    If the vehicle cannot reach the station on its current fuel, the station
    is marked unreachable and effective_cost is set to infinity so it sorts last.
    """
    transit_fuel = station.distance_miles / vehicle.mpg
    reachable = transit_fuel <= vehicle.tank_current

    if not reachable:
        return StationResult(
            station=station,
            effective_cost=float("inf"),
            gallons_purchased=0.0,
            fuel_burned_in_transit=transit_fuel,
            reachable=False,
        )

    gallons_purchased = vehicle.gallons_to_fill + transit_fuel
    effective_cost = gallons_purchased * station.price_per_gallon

    return StationResult(
        station=station,
        effective_cost=effective_cost,
        gallons_purchased=gallons_purchased,
        fuel_burned_in_transit=transit_fuel,
        reachable=True,
    )


def rank_stations(stations: list[Station], vehicle: VehicleParams) -> list[StationResult]:
    """
    Evaluate all stations and return them ranked by effective cost (ascending).
    Unreachable stations are appended after all reachable ones.
    """
    if not stations:
        raise CostCalcError("Station list is empty — nothing to rank.")

    results = [calculate_station_result(s, vehicle) for s in stations]

    reachable = sorted(
        [r for r in results if r.reachable],
        key=lambda r: r.effective_cost,
    )
    unreachable = [r for r in results if not r.reachable]

    ranked = reachable + unreachable

    best_cost = reachable[0].effective_cost if reachable else float("inf")
    for i, result in enumerate(ranked):
        result.rank = i + 1
        result.savings_vs_best = (
            best_cost - result.effective_cost if result.reachable else float("-inf")
        )

    return ranked


def recommend(stations: list[Station], vehicle: VehicleParams) -> Recommendation:
    """
    Top-level function: returns the best station and a full ranked list.

    Raises UnreachableStationError if no station can be reached on current fuel.
    """
    if vehicle.gallons_to_fill == 0:
        ranked = rank_stations(stations, vehicle)
        return Recommendation(
            best_station=ranked[0],
            all_results=ranked,
            vehicle=vehicle,
            tank_is_full=True,
            note="Tank is already full — no fill-up needed.",
        )

    ranked = rank_stations(stations, vehicle)
    reachable = [r for r in ranked if r.reachable]

    if not reachable:
        raise UnreachableStationError(
            f"No stations are reachable on current fuel. "
            f"Range remaining: {vehicle.range_remaining:.1f} miles."
        )

    best = reachable[0]
    note = _build_note(best, reachable)

    return Recommendation(
        best_station=best,
        all_results=ranked,
        vehicle=vehicle,
        note=note,
    )


def _build_note(best: StationResult, reachable: list[StationResult]) -> str:
    """Human-readable explanation of why the top-ranked station was chosen."""
    if len(reachable) == 1:
        return f"Only reachable station: {best.station.name}."

    runner_up = reachable[1]
    savings = runner_up.effective_cost - best.effective_cost  # always >= 0
    price_diff = runner_up.station.price_per_gallon - best.station.price_per_gallon

    if price_diff < 0:
        # best has higher price/gal but wins on total cost due to shorter drive
        return (
            f"{best.station.name} costs ${best.station.price_per_gallon:.3f}/gal "
            f"(${abs(price_diff):.3f} more per gallon than {runner_up.station.name}), "
            f"but saves ${savings:.2f} overall because it's closer."
        )
    else:
        return (
            f"{best.station.name} saves ${savings:.2f} vs {runner_up.station.name} "
            f"with a ${price_diff:.3f}/gal lower price."
        )
