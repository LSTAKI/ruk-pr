"""
Inventory Position and Accounting Module
Establishes standardized, mathematically rigorous inventory accounting:
- On-Hand: Physical recorded inventory.
- Reserved: Locked stock committed to pending fulfillment.
- Available: On-hand minus reserved (non-negative).
- Expired: Stock with expiry <= as_of_date or status == 'EXPIRED'.
- Usable: Available, unexpired, non-quarantined stock with shelf-life exceeding lead-time buffer.
- Incoming: Inventory in-transit (accounted for upon arrival).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple


class InventoryPositionAnalyzer:
    """Evaluates network inventory health, usable availability, and risk posture."""

    @staticmethod
    def evaluate_batch_accounting(
        batch: Dict[str, Any],
        as_of_date: datetime | None = None,
        lead_time_days: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Evaluates a single inventory batch against standard accounting rules.
        """
        if as_of_date is None:
            as_of_date = datetime.utcnow()

        on_hand = max(0, batch.get("on_hand_units", 0))
        reserved = max(0, batch.get("reserved_units", 0))
        # Clamp reserved so it never exceeds on-hand in accounting
        reserved = min(on_hand, reserved)
        available = on_hand - reserved

        expiry = batch.get("expiry_date")
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry)

        batch_status = batch.get("batch_status", "AVAILABLE").upper()
        min_freshness_date = as_of_date + timedelta(days=lead_time_days)

        is_expired = (expiry is not None and expiry <= as_of_date) or (batch_status == "EXPIRED")
        is_quarantined = (batch_status == "QUARANTINED")
        is_depleted = (on_hand == 0) or (batch_status == "DEPLETED")

        # Usable stock must be unexpired, unreserved, non-quarantined, with remaining shelf-life > lead time
        if is_expired or is_quarantined or is_depleted:
            usable = 0
            computed_status = "EXPIRED" if is_expired else ("QUARANTINED" if is_quarantined else "DEPLETED")
        elif expiry is not None and expiry <= min_freshness_date:
            # Near-expiry batch cannot survive transit lead time
            usable = 0
            computed_status = "SHELF_LIFE_INSUFFICIENT"
        else:
            usable = available
            computed_status = "AVAILABLE"

        return {
            "batch_lot": batch.get("batch_lot"),
            "warehouse_code": batch.get("warehouse_code"),
            "product_sku": batch.get("product_sku"),
            "on_hand_units": on_hand,
            "reserved_units": reserved,
            "available_units": available,
            "usable_units": usable,
            "is_expired": is_expired,
            "is_quarantined": is_quarantined,
            "status": computed_status,
        }

    @classmethod
    def calculate_warehouse_available_stock(
        cls,
        inventory_items: List[Dict[str, Any]],
        as_of_date: datetime | None = None,
        require_usable: bool = True,
        lead_time_days: float = 1.0,
    ) -> Dict[str, Dict[str, int]]:
        """
        Calculates usable (or available) units per warehouse and product SKU.
        Guarantees expired and quarantined batches are excluded from allocation.
        Returns: { warehouse_code: { sku: usable_units } }
        """
        if as_of_date is None:
            as_of_date = datetime.utcnow()

        stock_map: Dict[str, Dict[str, int]] = {}
        for item in inventory_items:
            eval_result = cls.evaluate_batch_accounting(
                item, as_of_date=as_of_date, lead_time_days=lead_time_days
            )
            wh = eval_result["warehouse_code"]
            sku = eval_result["product_sku"]
            qty = eval_result["usable_units"] if require_usable else eval_result["available_units"]

            if wh not in stock_map:
                stock_map[wh] = {}
            stock_map[wh][sku] = stock_map[wh].get(sku, 0) + qty

        return stock_map

    @staticmethod
    def identify_stockout_risks(
        demand_forecasts: List[Dict[str, Any]],
        destination_current_stock: Dict[str, Dict[str, int]] | None = None,
        critical_days_threshold: float = 3.0,
        lead_time_days_map: Dict[str, float] | None = None,
        safety_stock_days_map: Dict[str, float] | None = None,
    ) -> List[Dict[str, Any]]:
        """Flags products and destinations with elevated stockout risk.

        Risk categories (NOT calibrated probabilities):
          Critical        — cover_days == 0 (already out of stock)
          High            — 0 < cover_days <= lead_time_days
          Moderate        — lead_time_days < cover_days <= lead_time_days + ss_days
          Low             — cover_days > lead_time_days + ss_days
          InsufficientData — daily_demand == 0 or no history

        Backward compatibility: when lead_time_days_map is not provided,
        critical_days_threshold is used as the lead-time proxy (matches legacy
        behaviour with HIGH/MEDIUM renamed to HIGH; all below threshold → HIGH,
        all at/above → LOW).

        Parameters
        ----------
        demand_forecasts:
            List of forecast dicts (must contain destination_code, sku,
            daily_mean_demand, and optionally destination_name, product_name).
        destination_current_stock:
            {destination_code: {sku: units}}.  Defaults to empty (zero stock).
        critical_days_threshold:
            Legacy threshold used when lead_time_days_map is absent.
        lead_time_days_map:
            Optional {destination_code: lead_time_days} for 5-level scoring.
        safety_stock_days_map:
            Optional {destination_code_sku: safety_stock_days} for Moderate band.
        """
        if destination_current_stock is None:
            destination_current_stock = {}
        if lead_time_days_map is None:
            lead_time_days_map = {}
        if safety_stock_days_map is None:
            safety_stock_days_map = {}

        alerts = []
        for demand in demand_forecasts:
            dst_code = demand["destination_code"]
            sku = demand["sku"]
            daily_demand = demand.get("daily_mean_demand", 1.0)
            cur_stock = destination_current_stock.get(dst_code, {}).get(sku, 0)

            if daily_demand <= 0:
                risk_level = "InsufficientData"
                cover_days = None
            else:
                cover_days = round(cur_stock / daily_demand, 2)

                lead_t = lead_time_days_map.get(dst_code, critical_days_threshold)
                ss_key = f"{dst_code}_{sku}"
                ss_days = safety_stock_days_map.get(ss_key, 0.0)

                if cover_days <= 0.0:
                    risk_level = "Critical"
                elif cover_days <= lead_t:
                    risk_level = "High"
                elif cover_days <= lead_t + ss_days:
                    risk_level = "Moderate"
                else:
                    risk_level = "Low"

            alerts.append({
                "destination_code": dst_code,
                "destination_name": demand.get("destination_name", dst_code),
                "product_sku": sku,
                "product_name": demand.get("product_name", sku),
                "current_inventory_days": cover_days,
                "forecasted_daily_demand": round(daily_demand, 2),
                "risk_level": risk_level,
                # Legacy key kept for backward compat (same as risk_level)
                "risk_category": risk_level,
            })

        return alerts

    @staticmethod
    def calculate_cover_days(
        usable_units: int,
        daily_mean_demand: float,
    ) -> Optional[float]:
        """Returns estimated days of inventory cover, or None when demand is zero.

        cover_days = usable_units / daily_mean_demand

        Parameters
        ----------
        usable_units:
            Units available after excluding expired, quarantined, reserved.
        daily_mean_demand:
            Mean daily demand from the forecasting engine.

        Returns
        -------
        float (rounded to 2 dp) or None.
        """
        if daily_mean_demand <= 0:
            return None
        return round(usable_units / daily_mean_demand, 2)

