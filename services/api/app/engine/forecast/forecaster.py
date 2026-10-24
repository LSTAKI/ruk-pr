"""
Demand Forecasting Module
Forecasts destination-level product consumption across planning horizons.
"""

from typing import List, Dict, Any
import numpy as np

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
    """Computes destination-level demand expectations over an N-day horizon."""

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def forecast_demand(
        self,
        destinations: List[Dict[str, Any]],
        products: List[Dict[str, Any]],
        horizon_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Generates deterministic daily demand forecasts for each destination and product SKU.
        Returns a list of demand target dictionaries.
        """
        forecasts = []
        for dest in destinations:
            ch_factor = CHANNEL_DEMAND_FACTORS.get(dest.get("channel_type", "convenience"), 1.0)

            for prod in products:
                cat_factor = CATEGORY_VELOCITY.get(prod.get("category", "Snacks"), 1.0)
                # Base expected daily unit sales
                base_daily = 15.0 * ch_factor * cat_factor
                # Predict across horizon
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
                })

        return forecasts
