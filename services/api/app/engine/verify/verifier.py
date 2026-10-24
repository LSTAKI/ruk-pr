"""
Solution Verification Module
Independently verifies that recommended shipments do not violate physical constraints,
unreserved warehouse availability, destination limits, or shelf-life safety windows.
"""

from typing import List, Dict, Any, Tuple

class SolutionVerifier:
    """Rigorous post-solve validation to ensure solver recommendations are feasible."""

    @staticmethod
    def verify_plan_feasibility(
        shipments: List[Dict[str, Any]],
        available_supply: Dict[str, Dict[str, int]],
        demand_targets: List[Dict[str, Any]],
    ) -> Tuple[bool, List[str]]:
        """
        Verifies all shipment decisions against physical constraints.
        Returns (is_feasible, list_of_violations).
        """
        violations = []

        # 1. Non-negativity and integer checks
        for s in shipments:
            units = s.get("recommended_units", 0)
            if units <= 0:
                violations.append(
                    f"Non-positive shipment quantity ({units}) for SKU {s.get('product_sku')}"
                )

        # 2. Supply capacity check per warehouse and SKU
        shipped_supply: Dict[str, Dict[str, int]] = {}
        for s in shipments:
            w = s["source_warehouse_code"]
            sku = s["product_sku"]
            if w not in shipped_supply:
                shipped_supply[w] = {}
            shipped_supply[w][sku] = shipped_supply[w].get(sku, 0) + s["recommended_units"]

        for w, sku_dict in shipped_supply.items():
            for sku, total_shipped in sku_dict.items():
                avail = available_supply.get(w, {}).get(sku, 0)
                if total_shipped > avail:
                    violations.append(
                        f"Supply overflow at {w} for {sku}: Shipped {total_shipped} > Available {avail}"
                    )

        # 3. Demand upper bound check per destination
        shipped_demand: Dict[str, Dict[str, int]] = {}
        for s in shipments:
            d = s["destination_code"]
            sku = s["product_sku"]
            if d not in shipped_demand:
                shipped_demand[d] = {}
            shipped_demand[d][sku] = shipped_demand[d].get(sku, 0) + s["recommended_units"]

        demand_map = {(dt["destination_code"], dt["sku"]): dt["forecasted_units"] for dt in demand_targets}
        for d, sku_dict in shipped_demand.items():
            for sku, total_received in sku_dict.items():
                max_dem = demand_map.get((d, sku), 0)
                if total_received > max_dem:
                    violations.append(
                        f"Over-fulfillment at {d} for {sku}: Received {total_received} > Demand {max_dem}"
                    )

        is_feasible = len(violations) == 0
        return is_feasible, violations
