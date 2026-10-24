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
from typing import List, Dict, Any, Tuple

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
    ) -> List[Dict[str, Any]]:
        """
        Flags products and destinations with days-of-supply under threshold.
        """
        if destination_current_stock is None:
            destination_current_stock = {}

        alerts = []
        for demand in demand_forecasts:
            dst_code = demand["destination_code"]
            sku = demand["sku"]
            daily_demand = demand.get("daily_mean_demand", 1.0)
            cur_stock = destination_current_stock.get(dst_code, {}).get(sku, 0)

            cover_days = cur_stock / daily_demand if daily_demand > 0 else 99.0

            if cover_days <= critical_days_threshold:
                risk_level = "HIGH" if cover_days <= 1.0 else "MEDIUM"
                alerts.append({
                    "destination_code": dst_code,
                    "destination_name": demand.get("destination_name", dst_code),
                    "product_sku": sku,
                    "product_name": demand.get("product_name", sku),
                    "current_inventory_days": round(cover_days, 1),
                    "forecasted_daily_demand": round(daily_demand, 1),
                    "risk_level": risk_level,
                })

        return alerts
