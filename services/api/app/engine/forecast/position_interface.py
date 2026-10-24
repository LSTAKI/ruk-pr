"""
Demand Forecasting — Inventory Position Interface
=================================================

Provides the typed interface through which the planning engine can obtain
forecast demand for each product-destination combination.

Design constraints (explicitly documented)
-----------------------------------------
1. Forecast demand is NOT treated as existing inventory.
   ``forecast_demand_for_planning`` returns expected *future consumption*
   only.  Callers must subtract this from usable supply.

2. Historical demand is NOT double-counted.
   The function queries only the most recent ``lookback_days`` observations
   and projects them forward.  It does not add historical consumption to
   the forecast output.

3. Arrival lead times are passed through unchanged.
   The planning engine is responsible for accounting for lead time when
   deciding how much to ship; this module does not conflate forecast
   horizon with delivery lead time.

4. Expired / quarantined inventory exclusion is NOT the responsibility of
   this module.  ``InventoryPositionAnalyzer.calculate_warehouse_available_stock``
   handles that boundary.

5. The forecast horizon (H days of expected demand) must NOT be confused
   with the delivery lead time (L days until goods arrive).
   The two values are independent parameters.

Outstanding work before forecast-driven replenishment is production-ready
------------------------------------------------------------------------
  a) Safety-stock calibration: current implementation uses a deterministic
     flat forecast and does not model demand variance or service-level
     targets.  A safety-stock multiplier (e.g., z × σ_d × √L) should be
     added to the replenishment quantity before the optimizer runs.
  b) Lead-time uncertainty: lead times in the Route table are point
     estimates.  Probabilistic lead times would improve buffer calculations.
  c) Backorder / lost-sales policy: when the optimizer is infeasible
     (supply < demand), the policy for partial fulfilment or substitution
     has not been implemented.
  d) Multi-period rolling horizon: the current optimizer solves a single
     static period.  A rolling-horizon approach (MPC-style) would be needed
     for production-grade replenishment.

Backward-compatibility note
---------------------------
The dict keys returned by ``forecast_demand_for_planning`` exactly match
those consumed by the existing planning route and by
``InventoryPositionAnalyzer.identify_stockout_risks``.  No changes to
those callers are required.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.engine.forecast.data_prep import prepare_demand_series
from app.engine.forecast.methods import (
    METHOD_EWMA,
    SUPPORTED_HORIZONS,
    forecast,
)


# ---------------------------------------------------------------------------
# Typing alias for the planning-engine compatible dict format
# ---------------------------------------------------------------------------

PlanningForecastDict = Dict[str, Any]
"""Dict with the following guaranteed keys (for backward compat):

  destination_code:    str
  destination_name:    str
  sku:                 str
  product_name:        str
  category:            str
  horizon_days:        int
  daily_mean_demand:   float   ← used by identify_stockout_risks
  forecasted_units:    int     ← integer rounded for optimizer boundary
  method:              str
  warnings:            List[str]
  history_used:        int
"""


# ---------------------------------------------------------------------------
# Primary interface function
# ---------------------------------------------------------------------------

def forecast_demand_for_planning(
    demand_history_rows: List[Dict[str, Any]],
    destination_code: str,
    destination_name: str,
    product_sku: str,
    product_name: str,
    product_category: str,
    product_id: int,
    destination_id: int,
    horizon_days: int = 7,
    method: str = METHOD_EWMA,
    ewma_alpha: float = 0.3,
    as_of_date: Optional[date] = None,
) -> PlanningForecastDict:
    """Produces a planning-compatible forecast dict for a single product-destination.

    Parameters
    ----------
    demand_history_rows:
        Raw demand records for this product-destination pair (unfiltered;
        this function applies filtering itself).
    destination_code, destination_name:
        Identifiers for the destination.
    product_sku, product_name, product_category:
        Identifiers for the product.
    product_id, destination_id:
        Database IDs (not used in computation; carried through for traceability).
    horizon_days:
        Forecast horizon; must be in {7, 14, 30}.
    method:
        Forecasting method (default: 'ewma' for better noise smoothing).
    ewma_alpha:
        EWMA smoothing parameter.
    as_of_date:
        Forecast origin date; defaults to today (UTC).

    Returns
    -------
    PlanningForecastDict
        Always returns a result, even when history is insufficient
        (method_available=False produces a zero forecast with a warning).
    """
    if as_of_date is None:
        as_of_date = datetime.utcnow().date()

    if horizon_days not in SUPPORTED_HORIZONS:
        horizon_days = min(SUPPORTED_HORIZONS, key=lambda h: abs(h - horizon_days))

    # Prepare series (filtering and validation applied inside)
    series = prepare_demand_series(demand_history_rows, as_of_date=as_of_date)

    # Attempt the requested method; fall back to naïve if unavailable
    result = forecast(series, method, horizon_days, ewma_alpha=ewma_alpha)

    if not result.method_available:
        # Fall back to naïve
        from app.engine.forecast.methods import METHOD_NAIVE
        fallback = forecast(series, METHOD_NAIVE, horizon_days)
        if fallback.method_available:
            result = fallback
        else:
            # Absolute fallback: return zero forecast with warning
            return {
                "destination_code": destination_code,
                "destination_name": destination_name,
                "sku": product_sku,
                "product_name": product_name,
                "category": product_category,
                "horizon_days": horizon_days,
                "daily_mean_demand": 0.0,
                "forecasted_units": 0,
                "method": method,
                "method_available": False,
                "warnings": series.warnings + [
                    f"Insufficient history ({series.observation_count} observations). "
                    "Forecast set to zero; manual review required before planning."
                ],
                "history_used": series.observation_count,
            }

    # Round to integer at the planning boundary (see rounding_policy in methods.py)
    forecasted_units = max(0, round(result.total_demand))

    return {
        "destination_code": destination_code,
        "destination_name": destination_name,
        "sku": product_sku,
        "product_name": product_name,
        "category": product_category,
        "horizon_days": horizon_days,
        "daily_mean_demand": result.daily_mean_demand,
        "forecasted_units": forecasted_units,
        "method": result.method,
        "method_available": True,
        "warnings": result.warnings,
        "history_used": result.history_observations_used,
    }


# ---------------------------------------------------------------------------
# Batch query helper (for planning route use)
# ---------------------------------------------------------------------------

def build_forecast_lookup(
    demand_rows: List[Dict[str, Any]],
    destinations: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    horizon_days: int = 7,
    method: str = METHOD_EWMA,
    ewma_alpha: float = 0.3,
    as_of_date: Optional[date] = None,
) -> List[PlanningForecastDict]:
    """Builds a full planning forecast list for all destination × product pairs.

    Filters ``demand_rows`` in memory per (destination_id, product_id) pair
    rather than issuing N×M individual DB queries.  The caller is responsible
    for fetching ``demand_rows`` with a single targeted query.

    Parameters
    ----------
    demand_rows:
        All relevant demand history rows, each containing:
        ``destination_id``, ``product_id``, ``demand_date``,
        ``quantity_demanded``, ``quantity_sold``, ``is_simulated``.
    destinations:
        List of destination dicts (must contain ``id``, ``code``, ``name``).
    products:
        List of product dicts (must contain ``id``, ``sku``, ``name``, ``category``).
    horizon_days, method, ewma_alpha, as_of_date:
        Forwarded to ``forecast_demand_for_planning``.

    Returns
    -------
    List of PlanningForecastDict — same format as legacy BaselineDemandForecaster.
    """
    # Index rows by (destination_id, product_id) for O(1) lookup
    from collections import defaultdict
    row_index: Dict = defaultdict(list)
    for row in demand_rows:
        key = (int(row["destination_id"]), int(row["product_id"]))
        row_index[key].append(row)

    dest_map = {d["id"]: d for d in destinations}
    prod_map = {p["id"]: p for p in products}

    forecasts: List[PlanningForecastDict] = []
    for dest in destinations:
        for prod in products:
            rows = row_index[(dest["id"], prod["id"])]
            fc = forecast_demand_for_planning(
                demand_history_rows=rows,
                destination_code=dest["code"],
                destination_name=dest["name"],
                product_sku=prod["sku"],
                product_name=prod["name"],
                product_category=prod["category"],
                product_id=prod["id"],
                destination_id=dest["id"],
                horizon_days=horizon_days,
                method=method,
                ewma_alpha=ewma_alpha,
                as_of_date=as_of_date,
            )
            forecasts.append(fc)

    return forecasts
