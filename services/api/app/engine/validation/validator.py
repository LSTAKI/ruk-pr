"""
Validation Module
Validates inventory availability, destination demand parameters, shelf-life freshness,
active transportation routes, and physical throughput capacities.
"""

from typing import Dict, List, Any, Tuple
from datetime import datetime

class DistributionPlanValidator:
    """Validates FMCG distribution inputs and execution boundaries."""

    @staticmethod
    def validate_supply_and_demand(
        warehouses: List[Dict[str, Any]],
        inventory_items: List[Dict[str, Any]],
        demand_targets: List[Dict[str, Any]],
        as_of_date: datetime,
    ) -> Tuple[bool, List[str]]:
        """
        Validates supply, demand, and expiration integrity.
        Returns (is_valid, list_of_errors_or_warnings).
        """
        errors = []

        # 1. Check for negative inventory and reserved exceeding on-hand
        for item in inventory_items:
            on_hand = item.get("on_hand_units", 0)
            reserved = item.get("reserved_units", 0)
            batch_lot = item.get("batch_lot", "UNKNOWN")
            if on_hand < 0:
                errors.append(f"Negative on_hand_units ({on_hand}) in batch {batch_lot}")
            if reserved < 0:
                errors.append(f"Negative reserved_units ({reserved}) in batch {batch_lot}")
            if reserved > on_hand:
                errors.append(
                    f"Reserved units ({reserved}) exceed on-hand ({on_hand}) for batch {batch_lot}"
                )

        # 2. Check for expired or quarantined inventory items
        expired_count = 0
        quarantined_count = 0
        for item in inventory_items:
            expiry = item.get("expiry_date")
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry)
            if expiry and expiry <= as_of_date:
                expired_count += 1
            if item.get("batch_status") == "QUARANTINED":
                quarantined_count += 1

        if expired_count > 0:
            errors.append(f"Found {expired_count} expired inventory batches in supply pool")
        if quarantined_count > 0:
            errors.append(f"Found {quarantined_count} quarantined inventory batches in supply pool")

        # 3. Check demand consistency
        for d in demand_targets:
            units = d.get("forecasted_units", 0)
            if units < 0:
                errors.append(
                    f"Negative demand ({units}) for destination {d.get('destination_code')} sku {d.get('sku')}"
                )

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def validate_warehouse_capacities(
        warehouses: List[Dict[str, Any]],
        inventory_items: List[Dict[str, Any]],
    ) -> Tuple[bool, List[str]]:
        """Validates that warehouses do not exceed physical volumetric storage capacity."""
        errors = []
        cap_map = {w["code"]: w["capacity_units"] for w in warehouses}
        usage_map: Dict[str, int] = {w["code"]: 0 for w in warehouses}

        for item in inventory_items:
            wh = item["warehouse_code"]
            usage_map[wh] = usage_map.get(wh, 0) + item.get("on_hand_units", 0)

        for wh_code, usage in usage_map.items():
            max_cap = cap_map.get(wh_code, 0)
            if usage > max_cap:
                errors.append(
                    f"Warehouse {wh_code} exceeds storage capacity: {usage}/{max_cap} units stored"
                )

        return len(errors) == 0, errors

    @staticmethod
    def validate_throughput_capacities(
        shipments: List[Dict[str, Any]],
        warehouse_dispatch_limits: Dict[str, int],
        destination_receiving_limits: Dict[str, int],
    ) -> Tuple[bool, List[str]]:
        """Validates daily dispatch and intake capacity boundaries."""
        errors = []
        dispatch_sum: Dict[str, int] = {}
        receiving_sum: Dict[str, int] = {}

        for s in shipments:
            w = s["source_warehouse_code"]
            d = s["destination_code"]
            qty = s.get("recommended_units", 0)

            dispatch_sum[w] = dispatch_sum.get(w, 0) + qty
            receiving_sum[d] = receiving_sum.get(d, 0) + qty

        for w, qty in dispatch_sum.items():
            limit = warehouse_dispatch_limits.get(w, 999999)
            if qty > limit:
                errors.append(f"Warehouse {w} exceeds daily dispatch capacity: {qty} > {limit}")

        for d, qty in receiving_sum.items():
            limit = destination_receiving_limits.get(d, 999999)
            if qty > limit:
                errors.append(f"Destination {d} exceeds daily receiving capacity: {qty} > {limit}")

        return len(errors) == 0, errors
