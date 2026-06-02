"""
ml_optimizer.py — ML & optimization layer for the Gas Efficiency App.

Three capabilities built on top of costcalc.py:

1. PriceForecaster  — LinearRegression on lag features to predict next-day price.
2. StationClusterer — KMeans to group stations into geographic + price-tier clusters.
3. RouteOptimizer   — Greedy multi-stop road-trip fueling optimizer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Price Forecaster
# ---------------------------------------------------------------------------

@dataclass
class PriceRecord:
    """One day's observed price at a station."""
    day: int          # 0-indexed day number
    price: float      # $/gal
    day_of_week: int  # 0=Mon … 6=Sun


class PriceForecaster:
    """
    Predict tomorrow's gas price from lag features using linear regression.

    Features per observation:
        - price_lag1   (yesterday's price)
        - price_lag2   (two days ago)
        - day_of_week  (0–6)
        - price_ma3    (3-day moving average)

    Implemented from scratch with closed-form OLS so the notebook
    can explain the math cell-by-cell without hiding it in sklearn.
    The notebook also re-fits with sklearn to validate.
    """

    def __init__(self) -> None:
        self._coef: Optional[list[float]] = None
        self._intercept: float = 0.0
        self.feature_names = ["price_lag1", "price_lag2", "day_of_week", "price_ma3"]

    def _build_features(self, records: list[PriceRecord]) -> tuple[list[list[float]], list[float]]:
        """Return (X, y) starting from index 2 (needs 2 lags)."""
        X, y = [], []
        prices = [r.price for r in records]
        for i in range(2, len(records)):
            lag1 = prices[i - 1]
            lag2 = prices[i - 2]
            dow  = records[i].day_of_week
            ma3  = sum(prices[i - 2:i + 1]) / 3  # includes today (target leaks minimally)
            X.append([lag1, lag2, dow, ma3])
            y.append(prices[i])
        return X, y

    def fit(self, records: list[PriceRecord]) -> "PriceForecaster":
        """OLS closed-form: β = (XᵀX)⁻¹ Xᵀy (with bias column)."""
        if len(records) < 5:
            raise ValueError("Need ≥5 records to fit the forecaster.")
        X_raw, y = self._build_features(records)

        n = len(X_raw)
        p = len(X_raw[0]) + 1  # +1 for intercept column

        # Augment X with a leading 1 for the intercept
        X = [[1.0] + row for row in X_raw]

        # XᵀX  (p × p)
        XtX = [[sum(X[i][k] * X[i][j] for i in range(n)) for j in range(p)] for k in range(p)]
        # Xᵀy  (p × 1)
        Xty = [sum(X[i][k] * y[i] for i in range(n)) for k in range(p)]

        # Gaussian elimination to solve XtX @ beta = Xty
        beta = _solve_linear(XtX, Xty)
        self._intercept = beta[0]
        self._coef = beta[1:]
        return self

    def predict_next(self, recent: list[PriceRecord]) -> float:
        """Predict the price one day after the last record in *recent*."""
        if self._coef is None:
            raise RuntimeError("Call fit() first.")
        if len(recent) < 3:
            raise ValueError("Need ≥3 recent records for prediction.")

        prices = [r.price for r in recent]
        lag1 = prices[-1]
        lag2 = prices[-2]
        dow  = (recent[-1].day_of_week + 1) % 7
        ma3  = sum(prices[-3:]) / 3

        features = [lag1, lag2, dow, ma3]
        pred = self._intercept + sum(c * f for c, f in zip(self._coef, features))
        return round(pred, 4)

    @property
    def coef(self) -> list[float]:
        if self._coef is None:
            raise RuntimeError("Call fit() first.")
        return self._coef

    @property
    def intercept(self) -> float:
        return self._intercept


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting. Solves Ax = b in-place."""
    n = len(b)
    # Augment
    M = [A[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        # Pivot
        max_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[max_row] = M[max_row], M[col]
        pivot = M[col][col]
        if abs(pivot) < 1e-12:
            raise ValueError("Singular matrix — cannot solve OLS system.")
        for row in range(col + 1, n):
            factor = M[row][col] / pivot
            M[row] = [M[row][j] - factor * M[col][j] for j in range(n + 1)]
    # Back-substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


# ---------------------------------------------------------------------------
# 2. Station Clusterer
# ---------------------------------------------------------------------------

@dataclass
class GeoStation:
    """Minimal station representation for clustering."""
    name: str
    lat: float
    lon: float
    price: float


def cluster_stations(stations: list[GeoStation], k: int = 3, seed: int = 42) -> list[int]:
    """
    Assign each station to one of k clusters using k-means on
    (lat, lon, normalized_price).  Returns a list of cluster labels
    with the same length as *stations*.

    Price is normalised to [0, 1] and weighted ×2 so price tier
    influences cluster membership as strongly as geography.
    """
    if k > len(stations):
        raise ValueError(f"k ({k}) cannot exceed number of stations ({len(stations)}).")

    prices = [s.price for s in stations]
    p_min, p_range = min(prices), max(prices) - min(prices)
    p_range = p_range or 1.0

    def vec(s: GeoStation) -> list[float]:
        return [s.lat, s.lon, 2.0 * (s.price - p_min) / p_range]

    vectors = [vec(s) for s in stations]

    # Seeded deterministic initialisation (pick k evenly spaced)
    import random
    rng = random.Random(seed)
    indices = rng.sample(range(len(stations)), k)
    centroids = [vectors[i][:] for i in indices]

    labels = [0] * len(stations)
    for _ in range(100):
        # Assignment
        new_labels = [
            min(range(k), key=lambda c: _l2sq(v, centroids[c]))
            for v in vectors
        ]
        if new_labels == labels:
            break
        labels = new_labels
        # Update centroids
        for c in range(k):
            members = [vectors[i] for i, lbl in enumerate(labels) if lbl == c]
            if members:
                centroids[c] = [sum(m[d] for m in members) / len(members) for d in range(3)]

    return labels


def _l2sq(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# 3. Route Optimizer
# ---------------------------------------------------------------------------

@dataclass
class TripSegment:
    """One leg of a road trip with an available fueling stop."""
    name: str               # station or waypoint name
    cumulative_miles: float # total trip miles at this point
    price: float            # $/gal at this stop (inf if no station)
    has_station: bool = True


@dataclass
class FuelingDecision:
    """Output: where to fill up and how much."""
    segment: TripSegment
    gallons_to_add: float   # 0 = skip this stop
    reason: str


def optimize_route_fueling(
    segments: list[TripSegment],
    mpg: float,
    tank_capacity: float,
    tank_start: float,
    min_tank_fraction: float = 0.15,
) -> list[FuelingDecision]:
    """
    Greedy lookahead: at each station, decide whether to fill (and how much)
    based on whether the next cheaper station is reachable on current fuel.

    Strategy: fill to full only if this is the cheapest station reachable from here,
    otherwise top-up just enough to reach the next cheaper stop.

    Returns one FuelingDecision per segment.
    """
    decisions: list[FuelingDecision] = []
    tank = tank_start
    min_tank = tank_capacity * min_tank_fraction

    for i, seg in enumerate(segments):
        if not seg.has_station:
            decisions.append(FuelingDecision(seg, 0.0, "no station here"))
            # Consume fuel to next segment
            if i + 1 < len(segments):
                dist = segments[i + 1].cumulative_miles - seg.cumulative_miles
                tank -= dist / mpg
            continue

        # Lookahead: find next cheaper station reachable on a full tank
        cheaper_idx = None
        for j in range(i + 1, len(segments)):
            if not segments[j].has_station:
                continue
            dist_to_j = segments[j].cumulative_miles - seg.cumulative_miles
            can_reach_on_full = (tank_capacity * mpg) >= dist_to_j
            if segments[j].price < seg.price and can_reach_on_full:
                cheaper_idx = j
                break

        if cheaper_idx is None:
            # No cheaper reachable station ahead — fill to full
            added = tank_capacity - tank
            decisions.append(FuelingDecision(seg, added, "cheapest reachable stop ahead → fill to full"))
            tank = tank_capacity
        else:
            # A cheaper stop is coming — top up only to reach it safely
            dist_to_cheaper = segments[cheaper_idx].cumulative_miles - seg.cumulative_miles
            needed = dist_to_cheaper / mpg + min_tank  # +buffer
            top_up = max(0.0, needed - tank)
            top_up = min(top_up, tank_capacity - tank)
            reason = f"cheaper stop '{segments[cheaper_idx].name}' reachable → top-up only"
            decisions.append(FuelingDecision(seg, top_up, reason))
            tank += top_up

        # Consume fuel to next segment
        if i + 1 < len(segments):
            dist = segments[i + 1].cumulative_miles - seg.cumulative_miles
            tank -= dist / mpg
            tank = max(tank, 0.0)

    return decisions


def total_trip_cost(decisions: list[FuelingDecision]) -> float:
    """Sum of all fueling costs along the route."""
    return sum(d.gallons_to_add * d.segment.price for d in decisions)
