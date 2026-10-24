"""
Demand Forecasting — Backtesting and Evaluation
================================================

Evaluates forecasting accuracy using a strict chronological train/test split
(rolling-origin holdout) to prevent future-data leakage.

Evaluation protocol
-------------------
For each (product, destination) pair:
  1. Prepare the series with ``prepare_demand_series``.
  2. Split chronologically: earlier observations = train, later = test.
  3. Fit each supported method on the train partition.
  4. Evaluate against the test partition.

Metrics
-------
MAE (Mean Absolute Error)
  MAE = (1/N) · Σ |y_i − ŷ_i|
  where y_i is actual demand, ŷ_i is forecast, and N is the number of
  evaluated observations.

  Interpretation: average absolute deviation in the same units as demand.
  MAE is always defined as long as N ≥ 1.

WAPE (Weighted Absolute Percentage Error)
  WAPE = Σ |y_i − ŷ_i| / Σ y_i   (expressed as a percentage)
  Also known as wMAPE or aggregate APE.

  WAPE is undefined when the sum of actual demand is zero.
  When Σ y_i = 0, WAPE is reported as ``None`` to avoid division by zero
  and the ``wape_unavailable_reason`` field explains why.
  This is not an error — it occurs legitimately when all test observations
  are truly zero-demand days (e.g., seasonal product in off-season).

  WAPE was chosen over MAPE because MAPE is undefined for individual
  zero-demand observations (division by zero), whereas WAPE aggregates
  the sum and is numerically stable for most FMCG datasets.

Result guarantees
-----------------
* Forecast results used in evaluation are generated from the train partition
  ONLY.  The test partition is never seen during model fitting.
* A flat forecast (same value for all horizon steps) is used, consistent
  with how the naïve and EWMA methods work.
* Evaluation period and observation count are always reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from app.engine.forecast.data_prep import (
    MIN_HISTORY_EWMA,
    PreparedSeries,
    chronological_split,
    prepare_demand_series,
)
from app.engine.forecast.methods import (
    METHOD_EWMA,
    METHOD_NAIVE,
    METHOD_SEASONAL_NAIVE,
    SUPPORTED_METHODS,
    forecast,
    forecast_ewma,
    forecast_naive,
    forecast_seasonal_naive,
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MethodEvaluation:
    """Accuracy metrics for a single forecasting method on one series."""

    method: str
    method_available: bool
    unavailability_reason: Optional[str]

    mae: Optional[float]           # None if no test observations
    wape: Optional[float]          # None if sum of actuals == 0
    wape_unavailable_reason: Optional[str]

    n_evaluated: int               # Number of test observations evaluated
    evaluation_start: Optional[date]
    evaluation_end: Optional[date]


@dataclass
class SeriesEvaluation:
    """Backtesting results for a single product-destination series."""

    product_id: Optional[int]
    destination_id: Optional[int]
    product_sku: Optional[str]
    destination_code: Optional[str]

    train_observations: int
    test_observations: int
    total_observations: int
    evaluation_start: Optional[date]
    evaluation_end: Optional[date]

    methods: Dict[str, MethodEvaluation]   # method name → evaluation
    warnings: List[str]


@dataclass
class AggregateEvaluation:
    """Aggregate backtesting results across all evaluated series."""

    n_series_evaluated: int
    total_observations_evaluated: int
    methods: Dict[str, Dict]   # method → {mae_mean, wape_mean, ...}
    series_results: List[SeriesEvaluation]
    caveats: List[str]


# ---------------------------------------------------------------------------
# Internal metric helpers
# ---------------------------------------------------------------------------

def _compute_mae(actuals: List[float], forecasts_: List[float]) -> Optional[float]:
    n = len(actuals)
    if n == 0:
        return None
    return round(sum(abs(a - f) for a, f in zip(actuals, forecasts_)) / n, 4)


def _compute_wape(
    actuals: List[float], forecasts_: List[float]
) -> tuple[Optional[float], Optional[str]]:
    """Returns (wape_value, unavailability_reason).  wape_value is None when undefined."""
    sum_actual = sum(actuals)
    if sum_actual == 0.0:
        return (
            None,
            "WAPE is undefined because the sum of actual demand in the test period is zero. "
            "This occurs when all test observations are zero-demand days.",
        )
    ae = sum(abs(a - f) for a, f in zip(actuals, forecasts_))
    return round((ae / sum_actual) * 100.0, 4), None


# ---------------------------------------------------------------------------
# Single-series evaluator
# ---------------------------------------------------------------------------

def evaluate_series(
    series: PreparedSeries,
    ewma_alpha: float = 0.3,
    test_fraction: float = 0.2,
    min_test_days: int = 7,
    product_id: Optional[int] = None,
    destination_id: Optional[int] = None,
    product_sku: Optional[str] = None,
    destination_code: Optional[str] = None,
) -> SeriesEvaluation:
    """Backtests all supported methods on a single series using chronological split.

    Parameters
    ----------
    series:
        Full prepared demand series.
    ewma_alpha:
        EWMA smoothing parameter.
    test_fraction:
        Fraction of data reserved for testing.
    min_test_days:
        Minimum number of test-period observations.
    product_id, destination_id, product_sku, destination_code:
        Metadata for the result; not used in computation.

    Returns
    -------
    SeriesEvaluation
    """
    train, test = chronological_split(series, test_fraction, min_test_days)

    eval_start = test.records[0].demand_date if test.records else None
    eval_end = test.records[-1].demand_date if test.records else None

    method_results: Dict[str, MethodEvaluation] = {}

    for method_name in SUPPORTED_METHODS:
        # Fit only on train partition; forecast_origin = last train date
        train_origin = train.records[-1].demand_date if train.records else None
        # We use a single-step flat forecast — the test horizon equals len(test)
        horizon = test.observation_count if test.observation_count > 0 else 1
        # Clamp horizon to max supported to avoid ValueError
        from app.engine.forecast.methods import SUPPORTED_HORIZONS
        # Use the smallest supported horizon >= horizon, or 30 if all smaller
        eval_horizon = 30   # Evaluation uses 30d max; we take the first N values
        try:
            result = forecast(
                train, method_name, eval_horizon,
                forecast_origin=train_origin,
                ewma_alpha=ewma_alpha,
            )
        except ValueError as exc:
            method_results[method_name] = MethodEvaluation(
                method=method_name,
                method_available=False,
                unavailability_reason=str(exc),
                mae=None, wape=None, wape_unavailable_reason=None,
                n_evaluated=0, evaluation_start=None, evaluation_end=None,
            )
            continue

        if not result.method_available:
            method_results[method_name] = MethodEvaluation(
                method=method_name,
                method_available=False,
                unavailability_reason=result.unavailability_reason,
                mae=None, wape=None, wape_unavailable_reason=None,
                n_evaluated=0, evaluation_start=eval_start, evaluation_end=eval_end,
            )
            continue

        # Match forecast length to test length
        actuals = [float(r.quantity_demanded) for r in test.records]
        flat_val = result.daily_mean_demand  # flat projection value
        forecasts_ = [flat_val] * len(actuals)

        mae = _compute_mae(actuals, forecasts_)
        wape, wape_reason = _compute_wape(actuals, forecasts_)

        method_results[method_name] = MethodEvaluation(
            method=method_name,
            method_available=True,
            unavailability_reason=None,
            mae=mae,
            wape=wape,
            wape_unavailable_reason=wape_reason,
            n_evaluated=len(actuals),
            evaluation_start=eval_start,
            evaluation_end=eval_end,
        )

    return SeriesEvaluation(
        product_id=product_id,
        destination_id=destination_id,
        product_sku=product_sku,
        destination_code=destination_code,
        train_observations=train.observation_count,
        test_observations=test.observation_count,
        total_observations=series.observation_count,
        evaluation_start=eval_start,
        evaluation_end=eval_end,
        methods=method_results,
        warnings=list(series.warnings),
    )


# ---------------------------------------------------------------------------
# Aggregate evaluator
# ---------------------------------------------------------------------------

def aggregate_evaluations(
    series_results: List[SeriesEvaluation],
) -> AggregateEvaluation:
    """Aggregates multiple per-series evaluation results.

    Computes mean MAE and mean WAPE per method across all series where the
    method was available.  Does NOT claim one method is superior unless the
    data supports it; instead, reports the numeric results and leaves
    interpretation to the consumer.

    Parameters
    ----------
    series_results:
        List of per-series evaluation results.

    Returns
    -------
    AggregateEvaluation
    """
    method_mae: Dict[str, List[float]] = {m: [] for m in SUPPORTED_METHODS}
    method_wape: Dict[str, List[float]] = {m: [] for m in SUPPORTED_METHODS}
    total_obs = 0

    for sr in series_results:
        for method_name, eval_ in sr.methods.items():
            if eval_.method_available and eval_.mae is not None:
                method_mae[method_name].append(eval_.mae)
            if eval_.method_available and eval_.wape is not None:
                method_wape[method_name].append(eval_.wape)
        total_obs += sr.test_observations

    agg_methods: Dict[str, Dict] = {}
    for method_name in SUPPORTED_METHODS:
        maes = method_mae[method_name]
        wapes = method_wape[method_name]
        agg_methods[method_name] = {
            "series_with_method": len(maes),
            "mae_mean": round(sum(maes) / len(maes), 4) if maes else None,
            "mae_min": round(min(maes), 4) if maes else None,
            "mae_max": round(max(maes), 4) if maes else None,
            "wape_mean_pct": round(sum(wapes) / len(wapes), 4) if wapes else None,
            "wape_min_pct": round(min(wapes), 4) if wapes else None,
            "wape_max_pct": round(max(wapes), 4) if wapes else None,
            "wape_series_with_zero_actuals": len(maes) - len(wapes),
        }

    caveats = [
        "All results are derived from deterministically simulated FMCG data, "
        "not from real business observations.",
        "Metrics should not be used to make deployment decisions without validation "
        "against real demand data.",
        "WAPE is unavailable for series where all test-period actual demand values are zero.",
        "Method comparison is numerical only; no method is declared superior without "
        "statistically significant evidence.",
    ]

    return AggregateEvaluation(
        n_series_evaluated=len(series_results),
        total_observations_evaluated=total_obs,
        methods=agg_methods,
        series_results=series_results,
        caveats=caveats,
    )
