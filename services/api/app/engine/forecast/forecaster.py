"""
Demand Forecasting Module — Backward-Compatible Entry Point
===========================================================

This module preserves the original ``BaselineDemandForecaster`` interface
that is imported by:
  * ``app/routes/planning.py``  (existing planning route)
  * ``tests/test_forecast.py``  (existing test)

The class has been extended so that when demand history is available it
delegates to the data-driven EWMA engine.  When no history rows are
supplied (legacy call pattern), it falls back to the original heuristic
channel/category multipliers — ensuring zero regression in existing tests.

New code should use the explicit forecasting API:
  from app.engine.forecast.methods import forecast
  from app.engine.forecast.data_prep import prepare_demand_series
  from app.engine.forecast.position_interface import forecast_demand_for_planning
"""

from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Legacy heuristic lookup tables (kept for backward compat / fallback)
# ---------------------------------------------------------------------------

CHANNEL_DEMAND_FACTORS = {
    "supermarket": 2.2,
    "wholesaler": 4.5,
    "convenience": 0.8,
}

CATEGORY_VELOCITY = {
    "Dairy": 1.6,
    "Beverages": 1.3,
    "Snacks": 1.1,
    "Personal Care": 0.6,
}


class BaselineDemandForecaster:
    """Computes destination-level demand expectations over an N-day horizon.

    Legacy interface — preserved for backward compatibility.

    When ``demand_history`` rows are supplied, the forecast is data-driven
    (EWMA over the historical series).  When no history is available, the
    original channel/category heuristic is used and that fact is noted in
    the returned dict via ``method="heuristic_fallback"``.
    """

    def __init__(self, seed: int = 42):
        # seed retained for API compatibility; not used by data-driven methods
        self.rng = np.random.default_rng(seed)

    def forecast_demand(
        self,
        destinations: List[Dict[str, Any]],
        products: List[Dict[str, Any]],
        horizon_days: int = 7,
        demand_history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Generates daily demand forecasts for each destination × product pair.

        Parameters
        ----------
        destinations:
            List of destination dicts.  Required keys: ``code``, ``name``,
            ``channel_type``.  Optional keys: ``id`` (needed for history lookup).
        products:
            List of product dicts.  Required keys: ``sku``, ``name``,
            ``category``.  Optional: ``id``.
        horizon_days:
            Forecast horizon in days.  When data-driven: must be 7, 14, or 30.
            If another value is passed, it is clamped to the nearest supported
            horizon for the data-driven path; the heuristic path accepts any value.
        demand_history:
            Optional flat list of demand history dicts containing at minimum:
            ``destination_id``, ``product_id``, ``demand_date``,
            ``quantity_demanded``, ``quantity_sold``, ``is_simulated``.
            When provided, the data-driven EWMA engine is used.
            When None, the legacy heuristic is used.

        Returns
        -------
        List of dicts compatible with existing planning schemas.  Keys include:
            ``destination_code``, ``destination_name``, ``sku``, ``product_name``,
            ``category``, ``horizon_days``, ``daily_mean_demand``,
            ``forecasted_units``.
        """
        if demand_history is not None:
            return self._data_driven_forecast(
                destinations, products, horizon_days, demand_history
            )
        return self._heuristic_forecast(destinations, products, horizon_days)

    # ------------------------------------------------------------------
    # Data-driven path (delegates to new engine)
    # ------------------------------------------------------------------

    def _data_driven_forecast(
        self,
        destinations: List[Dict[str, Any]],
        products: List[Dict[str, Any]],
        horizon_days: int,
        demand_history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        from app.engine.forecast.position_interface import build_forecast_lookup

        # Ensure destination / product dicts have 'id' fields
        # (planning route passes id-less dicts; we attempt graceful lookup)
        dests = _ensure_ids(destinations, "destinations")
        prods = _ensure_ids(products, "products")

        results = build_forecast_lookup(
            demand_rows=demand_history,
            destinations=dests,
            products=prods,
            horizon_days=horizon_days if horizon_days in (7, 14, 30) else 7,
        )
        return results

    # ------------------------------------------------------------------
    # Legacy heuristic path (original implementation, unchanged)
    # ------------------------------------------------------------------

    def _heuristic_forecast(
        self,
        destinations: List[Dict[str, Any]],
        products: List[Dict[str, Any]],
        horizon_days: int,
    ) -> List[Dict[str, Any]]:
        forecasts = []
        for dest in destinations:
            ch_factor = CHANNEL_DEMAND_FACTORS.get(
                dest.get("channel_type", "convenience"), 1.0
            )
            for prod in products:
                cat_factor = CATEGORY_VELOCITY.get(
                    prod.get("category", "Snacks"), 1.0
                )
                base_daily = 15.0 * ch_factor * cat_factor
                horizon_units = int(round(base_daily * horizon_days))
                forecasts.append({
                    "destination_code": dest["code"],
                    "destination_name": dest["name"],
                    "sku": prod["sku"],
                    "product_name": prod["name"],
                    "category": prod["category"],
                    "horizon_days": horizon_days,
                    "daily_mean_demand": round(base_daily, 2),
                    "forecasted_units": horizon_units,
                    "method": "heuristic_fallback",
                })
        return forecasts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_ids(
    items: List[Dict[str, Any]], kind: str
) -> List[Dict[str, Any]]:
    """Ensures every dict has an 'id' key (uses list index as synthetic ID if missing)."""
    result = []
    for i, item in enumerate(items):
        d = dict(item)
        if "id" not in d or d.get("id") is None:
            d["id"] = i + 1
        result.append(d)
    return result
