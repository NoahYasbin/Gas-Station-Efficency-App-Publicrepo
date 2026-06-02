"""
Tests for costcalc.py — Gas Efficiency Cost Engine

Test naming convention: test_<what>_<condition>_<expected_outcome>

Key numbers used throughout (verify by hand):
  effective_cost = (gallons_to_fill + distance / mpg) * price_per_gallon
"""

import math
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from costcalc import (
    VehicleParams,
    Station,
    StationResult,
    Recommendation,
    calculate_station_result,
    rank_stations,
    recommend,
    CostCalcError,
    InvalidParamsError,
    UnreachableStationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def standard_vehicle():
    """20 MPG, 1 gal in tank, 13 gal capacity → 12 gal to fill."""
    return VehicleParams(mpg=20, tank_current=1.0, tank_capacity=13.0)


@pytest.fixture
def nearly_full_vehicle():
    """20 MPG, 12.5 gal in tank, 13 gal capacity → 0.5 gal to fill."""
    return VehicleParams(mpg=20, tank_current=12.5, tank_capacity=13.0)


@pytest.fixture
def full_tank_vehicle():
    """20 MPG, 13 gal in tank, 13 gal capacity → 0 gal to fill."""
    return VehicleParams(mpg=20, tank_current=13.0, tank_capacity=13.0)


@pytest.fixture
def close_expensive():
    """1 mile away, $4.00/gal."""
    return Station(name="Close Expensive", price_per_gallon=4.00, distance_miles=1.0)


@pytest.fixture
def far_cheap():
    """20 miles away, $3.50/gal."""
    return Station(name="Far Cheap", price_per_gallon=3.50, distance_miles=20.0)


# ---------------------------------------------------------------------------
# VehicleParams validation
# ---------------------------------------------------------------------------


class TestVehicleParamsValidation:
    def test_valid_params_accepted(self):
        v = VehicleParams(mpg=30, tank_current=5.0, tank_capacity=15.0)
        assert v.mpg == 30
        assert v.gallons_to_fill == 10.0
        assert v.range_remaining == 150.0

    def test_full_tank_is_valid(self):
        v = VehicleParams(mpg=30, tank_current=15.0, tank_capacity=15.0)
        assert v.gallons_to_fill == 0.0

    def test_zero_current_fuel_is_valid(self):
        v = VehicleParams(mpg=30, tank_current=0.0, tank_capacity=15.0)
        assert v.range_remaining == 0.0

    def test_zero_mpg_raises(self):
        with pytest.raises(InvalidParamsError, match="MPG must be positive"):
            VehicleParams(mpg=0, tank_current=5.0, tank_capacity=15.0)

    def test_negative_mpg_raises(self):
        with pytest.raises(InvalidParamsError, match="MPG must be positive"):
            VehicleParams(mpg=-10, tank_current=5.0, tank_capacity=15.0)

    def test_zero_tank_capacity_raises(self):
        with pytest.raises(InvalidParamsError, match="Tank capacity must be positive"):
            VehicleParams(mpg=30, tank_current=0.0, tank_capacity=0.0)

    def test_negative_current_fuel_raises(self):
        with pytest.raises(InvalidParamsError, match="cannot be negative"):
            VehicleParams(mpg=30, tank_current=-1.0, tank_capacity=15.0)

    def test_current_exceeds_capacity_raises(self):
        with pytest.raises(InvalidParamsError, match="exceeds"):
            VehicleParams(mpg=30, tank_current=16.0, tank_capacity=15.0)


# ---------------------------------------------------------------------------
# Station validation
# ---------------------------------------------------------------------------


class TestStationValidation:
    def test_valid_station_accepted(self):
        s = Station(name="Shell", price_per_gallon=3.99, distance_miles=2.5)
        assert s.name == "Shell"

    def test_zero_price_raises(self):
        with pytest.raises(InvalidParamsError, match="Price must be positive"):
            Station(name="Shell", price_per_gallon=0.0, distance_miles=2.5)

    def test_negative_price_raises(self):
        with pytest.raises(InvalidParamsError, match="Price must be positive"):
            Station(name="Shell", price_per_gallon=-1.0, distance_miles=2.5)

    def test_negative_distance_raises(self):
        with pytest.raises(InvalidParamsError, match="Distance cannot be negative"):
            Station(name="Shell", price_per_gallon=3.99, distance_miles=-0.5)

    def test_zero_distance_is_valid(self):
        # e.g., user is already at the station
        s = Station(name="Shell", price_per_gallon=3.99, distance_miles=0.0)
        assert s.distance_miles == 0.0

    def test_negative_drive_time_raises(self):
        with pytest.raises(InvalidParamsError, match="Drive time cannot be negative"):
            Station(name="Shell", price_per_gallon=3.99, distance_miles=2.5, drive_time_minutes=-5)

    def test_none_drive_time_is_valid(self):
        s = Station(name="Shell", price_per_gallon=3.99, distance_miles=2.5, drive_time_minutes=None)
        assert s.drive_time_minutes is None


# ---------------------------------------------------------------------------
# calculate_station_result
# ---------------------------------------------------------------------------


class TestCalculateStationResult:
    def test_basic_cost_calculation(self):
        # 20 MPG, 1 gal current, 13 gal cap → 12 gal to fill
        # Station: 1 mile, $4.00/gal
        # transit_fuel = 1/20 = 0.05 gal
        # gallons_purchased = 12 + 0.05 = 12.05
        # effective_cost = 12.05 * 4.00 = $48.20
        vehicle = VehicleParams(mpg=20, tank_current=1.0, tank_capacity=13.0)
        station = Station(name="A", price_per_gallon=4.00, distance_miles=1.0)
        result = calculate_station_result(station, vehicle)

        assert result.reachable is True
        assert math.isclose(result.fuel_burned_in_transit, 0.05, rel_tol=1e-6)
        assert math.isclose(result.gallons_purchased, 12.05, rel_tol=1e-6)
        assert math.isclose(result.effective_cost, 48.20, rel_tol=1e-6)

    def test_station_at_zero_distance(self):
        # No transit cost — gallons_purchased equals gallons_to_fill exactly
        vehicle = VehicleParams(mpg=25, tank_current=3.0, tank_capacity=13.0)
        station = Station(name="Here", price_per_gallon=3.80, distance_miles=0.0)
        result = calculate_station_result(station, vehicle)

        assert result.reachable is True
        assert result.fuel_burned_in_transit == 0.0
        assert math.isclose(result.gallons_purchased, 10.0, rel_tol=1e-6)
        assert math.isclose(result.effective_cost, 38.0, rel_tol=1e-6)

    def test_unreachable_station_marked_correctly(self):
        # 0.5 gal in tank, 20 MPG → range = 10 miles. Station is 15 miles away.
        vehicle = VehicleParams(mpg=20, tank_current=0.5, tank_capacity=13.0)
        station = Station(name="Far", price_per_gallon=3.50, distance_miles=15.0)
        result = calculate_station_result(station, vehicle)

        assert result.reachable is False
        assert result.effective_cost == float("inf")
        assert result.gallons_purchased == 0.0
        # transit_fuel is still reported even when unreachable
        assert math.isclose(result.fuel_burned_in_transit, 0.75, rel_tol=1e-6)

    def test_exactly_enough_fuel_to_reach(self):
        # Exactly on the boundary — vehicle has exactly enough fuel to reach
        # tank_current=0.5, mpg=20 → range=10 miles; station at exactly 10 miles
        vehicle = VehicleParams(mpg=20, tank_current=0.5, tank_capacity=13.0)
        station = Station(name="Edge", price_per_gallon=3.50, distance_miles=10.0)
        result = calculate_station_result(station, vehicle)

        assert result.reachable is True
        assert math.isclose(result.fuel_burned_in_transit, 0.5, rel_tol=1e-6)

    def test_effective_price_per_gallon_property(self):
        vehicle = VehicleParams(mpg=20, tank_current=1.0, tank_capacity=13.0)
        station = Station(name="A", price_per_gallon=4.00, distance_miles=1.0)
        result = calculate_station_result(station, vehicle)

        # effective_price = effective_cost / gallons_purchased = 48.20 / 12.05 = 4.00
        # (same as listed price because cost = gallons * price — always equal by construction)
        assert math.isclose(result.effective_price_per_gallon, 4.00, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# rank_stations: core business logic tests
# ---------------------------------------------------------------------------


class TestRankStations:
    def test_empty_station_list_raises(self, standard_vehicle):
        with pytest.raises(CostCalcError, match="empty"):
            rank_stations([], standard_vehicle)

    def test_single_station_ranked_first(self, standard_vehicle):
        station = Station(name="Only", price_per_gallon=3.99, distance_miles=2.0)
        ranked = rank_stations([station], standard_vehicle)

        assert len(ranked) == 1
        assert ranked[0].rank == 1
        assert ranked[0].savings_vs_best == 0.0

    def test_cheaper_nearby_station_beats_far_cheap(self):
        """
        Nearly-full tank: filling just 0.5 gal means transit cost dominates.
        Close expensive station should win.

        Vehicles: 20 MPG, 12.5 gal current, 13 gal cap → 0.5 gal to fill
        Close ($4.00, 1 mi):  cost = (0.5 + 0.05) * 4.00 = 0.55 * 4.00 = $2.20
        Far   ($3.50, 20 mi): cost = (0.5 + 1.00) * 3.50 = 1.50 * 3.50 = $5.25
        → Close wins despite higher per-gallon price.
        """
        vehicle = VehicleParams(mpg=20, tank_current=12.5, tank_capacity=13.0)
        close = Station(name="Close", price_per_gallon=4.00, distance_miles=1.0)
        far = Station(name="Far", price_per_gallon=3.50, distance_miles=20.0)

        ranked = rank_stations([close, far], vehicle)

        assert ranked[0].station.name == "Close"
        assert ranked[1].station.name == "Far"
        assert math.isclose(ranked[0].effective_cost, 2.20, rel_tol=1e-6)
        assert math.isclose(ranked[1].effective_cost, 5.25, rel_tol=1e-6)

    def test_far_cheap_station_beats_close_expensive(self):
        """
        Near-empty tank: filling 12 gal means price dominates transit cost.
        Far cheaper station should win.

        Vehicle: 20 MPG, 1 gal current, 13 gal cap → 12 gal to fill
        Close ($4.00, 1 mi):  cost = (12 + 0.05) * 4.00 = 12.05 * 4.00 = $48.20
        Far   ($3.50, 20 mi): cost = (12 + 1.00) * 3.50 = 13.00 * 3.50 = $45.50
        → Far wins: $2.70 savings despite longer drive.
        """
        vehicle = VehicleParams(mpg=20, tank_current=1.0, tank_capacity=13.0)
        close = Station(name="Close", price_per_gallon=4.00, distance_miles=1.0)
        far = Station(name="Far", price_per_gallon=3.50, distance_miles=20.0)

        ranked = rank_stations([close, far], vehicle)

        assert ranked[0].station.name == "Far"
        assert ranked[1].station.name == "Close"
        assert math.isclose(ranked[0].effective_cost, 45.50, rel_tol=1e-6)
        assert math.isclose(ranked[1].effective_cost, 48.20, rel_tol=1e-6)

    def test_savings_vs_best_is_zero_for_rank1(self, standard_vehicle):
        stations = [
            Station(name="A", price_per_gallon=3.50, distance_miles=5.0),
            Station(name="B", price_per_gallon=4.00, distance_miles=1.0),
        ]
        ranked = rank_stations(stations, standard_vehicle)

        assert ranked[0].savings_vs_best == 0.0

    def test_savings_vs_best_is_negative_for_worse_stations(self, standard_vehicle):
        stations = [
            Station(name="A", price_per_gallon=3.50, distance_miles=5.0),
            Station(name="B", price_per_gallon=4.00, distance_miles=1.0),
        ]
        ranked = rank_stations(stations, standard_vehicle)

        assert ranked[1].savings_vs_best < 0

    def test_unreachable_stations_sorted_to_end(self):
        """Unreachable stations appear after all reachable ones, regardless of price."""
        vehicle = VehicleParams(mpg=20, tank_current=0.3, tank_capacity=13.0)
        # range = 6 miles
        near = Station(name="Near", price_per_gallon=4.50, distance_miles=2.0)      # reachable
        far = Station(name="Far", price_per_gallon=2.00, distance_miles=20.0)       # not reachable

        ranked = rank_stations([near, far], vehicle)

        assert ranked[0].station.name == "Near"
        assert ranked[0].reachable is True
        assert ranked[1].station.name == "Far"
        assert ranked[1].reachable is False
        assert ranked[1].effective_cost == float("inf")
        assert ranked[1].savings_vs_best == float("-inf")

    def test_multiple_stations_correct_order(self):
        """Three stations ordered correctly by effective cost."""
        vehicle = VehicleParams(mpg=25, tank_current=5.0, tank_capacity=15.0)
        # g_fill = 10 gal

        # Station A: 2 mi, $3.80 → cost = (10 + 0.08) * 3.80 = $38.304
        # Station B: 5 mi, $3.60 → cost = (10 + 0.20) * 3.60 = $36.72
        # Station C: 12 mi, $3.40 → cost = (10 + 0.48) * 3.40 = $35.632
        a = Station(name="A", price_per_gallon=3.80, distance_miles=2.0)
        b = Station(name="B", price_per_gallon=3.60, distance_miles=5.0)
        c = Station(name="C", price_per_gallon=3.40, distance_miles=12.0)

        ranked = rank_stations([a, b, c], vehicle)

        assert [r.station.name for r in ranked] == ["C", "B", "A"]
        assert math.isclose(ranked[0].effective_cost, 35.632, rel_tol=1e-4)
        assert math.isclose(ranked[1].effective_cost, 36.72, rel_tol=1e-4)
        assert math.isclose(ranked[2].effective_cost, 38.304, rel_tol=1e-4)

    def test_ranks_are_sequential(self, standard_vehicle):
        stations = [
            Station(name="A", price_per_gallon=3.50, distance_miles=5.0),
            Station(name="B", price_per_gallon=3.70, distance_miles=3.0),
            Station(name="C", price_per_gallon=4.00, distance_miles=1.0),
        ]
        ranked = rank_stations(stations, standard_vehicle)

        assert [r.rank for r in ranked] == [1, 2, 3]


# ---------------------------------------------------------------------------
# recommended integration + edge cases
# ---------------------------------------------------------------------------


class TestRecommend:
    def test_returns_best_station(self, standard_vehicle):
        close = Station(name="Close", price_per_gallon=4.00, distance_miles=1.0)
        far = Station(name="Far", price_per_gallon=3.50, distance_miles=20.0)

        rec = recommend([close, far], standard_vehicle)

        assert rec.best_station.station.name == "Far"
        assert rec.tank_is_full is False

    def test_full_tank_sets_flag_and_note(self, full_tank_vehicle):
        station = Station(name="Shell", price_per_gallon=3.99, distance_miles=2.0)
        rec = recommend([station], full_tank_vehicle)

        assert rec.tank_is_full is True
        assert "full" in rec.note.lower()

    def test_all_unreachable_raises(self):
        vehicle = VehicleParams(mpg=20, tank_current=0.1, tank_capacity=13.0)
        # range = 2 miles; all stations farther than that
        stations = [
            Station(name="A", price_per_gallon=3.50, distance_miles=5.0),
            Station(name="B", price_per_gallon=3.00, distance_miles=10.0),
        ]
        with pytest.raises(UnreachableStationError, match="Range remaining"):
            recommend(stations, vehicle)

    def test_note_explains_closer_wins(self, nearly_full_vehicle):
        """When a nearby pricier station wins on total cost, note should mention it's closer."""
        close = Station(name="Close", price_per_gallon=4.00, distance_miles=1.0)
        far = Station(name="Far", price_per_gallon=3.50, distance_miles=20.0)

        rec = recommend([close, far], nearly_full_vehicle)

        assert rec.best_station.station.name == "Close"
        assert "closer" in rec.note.lower()

    def test_note_explains_price_advantage(self, standard_vehicle):
        """When far cheaper station wins on total cost, note should mention price advantage."""
        close = Station(name="Close", price_per_gallon=4.00, distance_miles=1.0)
        far = Station(name="Far", price_per_gallon=3.50, distance_miles=20.0)

        rec = recommend([close, far], standard_vehicle)

        assert rec.best_station.station.name == "Far"
        assert "saves" in rec.note.lower()

    def test_single_station_only_option_note(self, standard_vehicle):
        station = Station(name="Only", price_per_gallon=3.99, distance_miles=2.0)
        rec = recommend([station], standard_vehicle)

        assert rec.best_station.station.name == "Only"
        assert "only" in rec.note.lower()

    def test_all_results_length_matches_input(self, standard_vehicle):
        stations = [
            Station(name="A", price_per_gallon=3.50, distance_miles=1.0),
            Station(name="B", price_per_gallon=3.60, distance_miles=2.0),
            Station(name="C", price_per_gallon=3.70, distance_miles=3.0),
        ]
        rec = recommend(stations, standard_vehicle)

        assert len(rec.all_results) == 3

    def test_vehicle_attached_to_recommendation(self, standard_vehicle):
        station = Station(name="A", price_per_gallon=3.99, distance_miles=1.0)
        rec = recommend([station], standard_vehicle)

        assert rec.vehicle is standard_vehicle

    def test_mixed_reachable_unreachable(self):
        """recommend() succeeds when at least one station is reachable."""
        vehicle = VehicleParams(mpg=20, tank_current=0.5, tank_capacity=13.0)
        # range = 10 miles
        near = Station(name="Near", price_per_gallon=4.50, distance_miles=5.0)
        far = Station(name="Far", price_per_gallon=2.00, distance_miles=50.0)

        rec = recommend([near, far], vehicle)

        assert rec.best_station.station.name == "Near"
        assert len(rec.all_results) == 2
        assert rec.all_results[1].reachable is False
