"""
Demand Forecasting — Core Methods
==================================

Implements three forecasting methods against a prepared demand series:

  A. Naïve baseline
     Forecast = last observed demand value, replicated across the horizon.
     Mathematical definition: ŷ(t+h) = y(T) for all h = 1 … H
     where T is the index of the most recent observation.

  B. EWMA (Exponentially Weighted Moving Average)
     Applies exponential smoothing to the ordered history.
     Mathematical definition:
       s(1) = y(1)
       s(t) = α·y(t) + (1−α)·s(t−1)   for t = 2, 3, …, T
       ŷ(t+h) = s(T)   for all h = 1 … H
     where α ∈ (0, 1] is the smoothing parameter.
     A higher α makes the forecast more sensitive to recent observations.
     A lower α puts more weight on the historical average, smoothing out noise.
     Default: α = 0.3 (moderate responsiveness, suitable for stable FMCG demand).

  C. Seasonal-naïve baseline (weekly, optional)
     Uses the demand value from the same weekday seven days prior.
     Mathematical definition: ŷ(t+h) = y(T − (7 − ((h−1) mod 7)))
     Requires at least 14 days of history (two full weeks).
     If insufficient history exists, this method returns ``method_available=False``
     with a clear explanation rather than fabricating a result.

Rounding policy
---------------
Forecast values are returned as ``float`` (with two decimal places) within the
forecasting layer to preserve precision.  Integer rounding (``math.ceil`` or
``round``) is applied at the **optimizer boundary** inside
``engine/optimize/solver.py`` where unit-integer shipments are required.
This separation is intentional and documented.

Determinism guarantee
---------------------
All methods are pure functions of their inputs.  Given identical
``PreparedSeries`` and parameters, the output is always identical.
No random state is used in the forecasting layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from app.engine.forecast.data_prep import (
    MIN_HISTORY_EWMA,
    MIN_HISTORY_NAIVE,
    MIN_HISTORY_SEASONAL,
    WARN_INSUFFICIENT_HISTORY,
    PreparedSeries,
)


# ---------------------------------------------------------------------------
# Supported methods
# ---------------------------------------------------------------------------

METHOD_NAIVE = "naive"
METHOD_EWMA = "ewma"
METHOD_SEASONAL_NAIVE = "seasonal_naive"

SUPPORTED_METHODS = (METHOD_NAIVE, METHOD_EWMA, METHOD_SEASONAL_NAIVE)
SUPPORTED_HORIZONS = (7, 14, 30)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    """Full output of a single forecast computation.

    Attributes
    ----------
    method:
        Name of the forecasting method used.
    method_available:
        False if the method could not be applied (e.g., insufficient history).
    unavailability_reason:
        Human-readable explanation when ``method_available=False``.
    horizon_days:
        Requested forecast horizon.
    daily_forecasts:
        Ordered list of (forecast_date, forecast_value) for each day in the horizon.
        Values are non-negative floats; precision is maintained here.
    total_demand:
        Sum of daily forecast values over the horizon (float, 2 dp).
    daily_mean_demand:
        Mean daily demand over the horizon (float, 2 dp).
        Used by the inventory-position interface (backward-compatible key).
    history_observations_used:
        Number of historical observations that informed the forecast.
    warnings:
        Data-quality warnings inherited from the PreparedSeries.
    """

    method: str
    method_available: bool
    unavailability_reason: Optional[str]
    horizon_days: int
    daily_forecasts: List[Dict]   # [{"date": date, "value": float}]
    total_demand: float
    daily_mean_demand: float
    history_observations_used: int
    warnings: List[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp_non_negative(value: float) -> float:
    """Ensures forecast values are non-negative (floor at 0.0)."""
    return max(0.0, value)


def _round2(value: float) -> float:
    return round(value, 2)


def _build_horizon_dates(forecast_origin: date, horizon_days: int) -> List[date]:
    return [forecast_origin + timedelta(days=h + 1) for h in range(horizon_days)]


def _unavailable_result(
    method: str,
    horizon_days: int,
    reason: str,
    warnings: List[str],
) -> ForecastResult:
    return ForecastResult(
        method=method,
        method_available=False,
        unavailability_reason=reason,
        horizon_days=horizon_days,
        daily_forecasts=[],
        total_demand=0.0,
        daily_mean_demand=0.0,
        history_observations_used=0,
        warnings=warnings,
    )


def _build_result(
    method: str,
    horizon_days: int,
    forecast_origin: date,
    daily_values: List[float],
    series: PreparedSeries,
) -> ForecastResult:
    clamped = [_clamp_non_negative(v) for v in daily_values]
    horizon_dates = _build_horizon_dates(forecast_origin, horizon_days)
    daily_forecasts = [
        {"date": d, "value": _round2(v)}
        for d, v in zip(horizon_dates, clamped)
    ]
    total = _round2(sum(clamped))
    mean = _round2(total / horizon_days) if horizon_days > 0 else 0.0

    return ForecastResult(
        method=method,
        method_available=True,
        unavailability_reason=None,
        horizon_days=horizon_days,
        daily_forecasts=daily_forecasts,
        total_demand=total,
        daily_mean_demand=mean,
        history_observations_used=series.observation_count,
        warnings=list(series.warnings),
    )


# ---------------------------------------------------------------------------
# Method A — Naïve Baseline
# ---------------------------------------------------------------------------

def forecast_naive(
    series: PreparedSeries,
    horizon_days: int,
    forecast_origin: Optional[date] = None,
) -> ForecastResult:
    """Naïve baseline: ŷ(t+h) = y(T) for all h.

    Parameters
    ----------
    series:
        Prepared, validated demand series.
    horizon_days:
        Number of days ahead to forecast.  Must be in SUPPORTED_HORIZONS.
    forecast_origin:
        The date from which the forecast is issued.  Defaults to the last
        date in the series.

    Returns
    -------
    ForecastResult
    """
    if series.observation_count < MIN_HISTORY_NAIVE:
        return _unavailable_result(
            METHOD_NAIVE, horizon_days,
            f"Insufficient history: {series.observation_count} observation(s). "
            f"Naïve method requires at least {MIN_HISTORY_NAIVE}.",
            series.warnings,
        )

    origin = forecast_origin or series.records[-1].demand_date
    last_value = float(series.records[-1].quantity_demanded)
    daily_values = [last_value] * horizon_days
    return _build_result(METHOD_NAIVE, horizon_days, origin, daily_values, series)


# ---------------------------------------------------------------------------
# Method B — EWMA
# ---------------------------------------------------------------------------

def forecast_ewma(
    series: PreparedSeries,
    horizon_days: int,
    alpha: float = 0.3,
    forecast_origin: Optional[date] = None,
) -> ForecastResult:
    """EWMA: exponentially weighted moving average.

    The smoothed level s(T) is projected flat across the horizon.

    Parameters
    ----------
    series:
        Prepared, validated demand series.
    horizon_days:
        Forecast horizon in days.
    alpha:
        Smoothing parameter in (0, 1].
        Larger α → more weight on recent observations.
        Smaller α → smoother forecast less influenced by recent spikes.
        Default 0.3 is appropriate for moderately stable FMCG demand.
    forecast_origin:
        Forecast origin date.

    Returns
    -------
    ForecastResult
    """
    if not (0.0 < alpha <= 1.0):
        raise ValueError(f"EWMA alpha must be in (0, 1]. Got: {alpha}")

    if series.observation_count < MIN_HISTORY_EWMA:
        return _unavailable_result(
            METHOD_EWMA, horizon_days,
            f"Insufficient history: {series.observation_count} observation(s). "
            f"EWMA requires at least {MIN_HISTORY_EWMA} for meaningful smoothing.",
            series.warnings,
        )

    demands = series.demands
    # Initialise with first observation
    level = float(demands[0])
    for qty in demands[1:]:
        level = alpha * float(qty) + (1.0 - alpha) * level

    origin = forecast_origin or series.records[-1].demand_date
    daily_values = [level] * horizon_days
    return _build_result(METHOD_EWMA, horizon_days, origin, daily_values, series)


# ---------------------------------------------------------------------------
# Method C — Seasonal-Naïve (weekly)
# ---------------------------------------------------------------------------

def forecast_seasonal_naive(
    series: PreparedSeries,
    horizon_days: int,
    season_length: int = 7,
    forecast_origin: Optional[date] = None,
) -> ForecastResult:
    """Weekly seasonal-naïve: ŷ(t+h) = y(T − (7 − (h−1) mod 7)).

    For each forecast step h, uses the demand observed on the same weekday
    from the previous cycle (7 days earlier in the history).

    Requirement: at least ``season_length * 2`` (default 14) observations so
    that every weekday is seen at least once and there is a reliable reference.

    If the series does not meet this threshold, returns ``method_available=False``
    with an explanation instead of fabricating a result.

    Parameters
    ----------
    series:
        Prepared demand series.
    horizon_days:
        Forecast horizon.
    season_length:
        Seasonal period in days (default 7 = weekly).
    forecast_origin:
        Forecast origin date.

    Returns
    -------
    ForecastResult
    """
    if series.observation_count < MIN_HISTORY_SEASONAL:
        return _unavailable_result(
            METHOD_SEASONAL_NAIVE, horizon_days,
            f"Insufficient history: {series.observation_count} observation(s). "
            f"Weekly seasonal-naïve requires at least {MIN_HISTORY_SEASONAL} days "
            f"(two full {season_length}-day cycles) to have a reliable reference for "
            "each weekday.",
            series.warnings,
        )

    # Build a date→demand lookup for the reference window
    date_demand: Dict[date, int] = {
        r.demand_date: r.quantity_demanded for r in series.records
    }

    origin = forecast_origin or series.records[-1].demand_date
    daily_values: List[float] = []

    for h in range(1, horizon_days + 1):
        forecast_date = origin + timedelta(days=h)
        # Reference date: same weekday, one cycle prior
        reference_date = forecast_date - timedelta(days=season_length)

        if reference_date in date_demand:
            daily_values.append(float(date_demand[reference_date]))
        else:
            # Walk back up to 7 days to find the most recent same-weekday observation
            found = None
            for lag in range(season_length, season_length * 4 + 1, season_length):
                candidate = forecast_date - timedelta(days=lag)
                if candidate in date_demand:
                    found = float(date_demand[candidate])
                    break
            if found is not None:
                daily_values.append(found)
            else:
                # Fallback to series mean for this weekday
                target_weekday = forecast_date.weekday()
                same_weekday = [
                    r.quantity_demanded
                    for r in series.records
                    if r.demand_date.weekday() == target_weekday
                ]
                if same_weekday:
                    daily_values.append(float(sum(same_weekday) / len(same_weekday)))
                else:
                    # Ultimate fallback: overall mean
                    daily_values.append(float(sum(series.demands) / len(series.demands)))

    return _build_result(
        METHOD_SEASONAL_NAIVE, horizon_days, origin, daily_values, series
    )


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def forecast(
    series: PreparedSeries,
    method: str,
    horizon_days: int,
    forecast_origin: Optional[date] = None,
    ewma_alpha: float = 0.3,
    season_length: int = 7,
) -> ForecastResult:
    """Dispatch forecast to the requested method.

    Parameters
    ----------
    series:
        Prepared demand series.
    method:
        One of ``naive``, ``ewma``, ``seasonal_naive``.
    horizon_days:
        Must be in {7, 14, 30}.
    forecast_origin:
        Forecast issue date (defaults to last observed date in series).
    ewma_alpha:
        EWMA smoothing parameter (used only when method='ewma').
    season_length:
        Seasonal period for seasonal-naïve (default 7).

    Returns
    -------
    ForecastResult

    Raises
    ------
    ValueError
        If ``method`` or ``horizon_days`` is invalid.
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(
            f"Unsupported forecasting method '{method}'. "
            f"Supported: {SUPPORTED_METHODS}"
        )
    if horizon_days not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported horizon {horizon_days}. "
            f"Supported: {SUPPORTED_HORIZONS}"
        )

    if method == METHOD_NAIVE:
        return forecast_naive(series, horizon_days, forecast_origin)
    if method == METHOD_EWMA:
        return forecast_ewma(series, horizon_days, ewma_alpha, forecast_origin)
    if method == METHOD_SEASONAL_NAIVE:
        return forecast_seasonal_naive(series, horizon_days, season_length, forecast_origin)

    # Should never reach here
    raise ValueError(f"Unhandled method: {method}")
