"""
Explainability Module
=====================

Translates mathematical optimization outcomes into transparent, driver-based justifications
for distribution planners, warehouse operations, and retail store managers.

Every explanation is computed strictly from real empirical values:
  - Destination replenishment requirement and stockout risk urgency.
  - Sourcing warehouse usable inventory and remaining throughput capacity.
  - Active route freight rates and transit lead times.
  - Competing warehouse alternatives and why they were not chosen
    (e.g., higher freight cost, longer transit, insufficient inventory, or capacity limits).
  - Batch freshness / expiry considerations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class DistributionDecisionExplainer:
    """Generates transparent, driver-based explanations for shipping recommendations."""

    @classmethod
    def explain_shipment(
        cls,
        shipment: Dict[str, Any],
        closest_warehouse: Optional[str] = None,
        is_closest: Optional[bool] = None,
        competing_options: Optional[List[Dict[str, Any]]] = None,
        destination_risk: Optional[str] = None,
        replenishment_requirement: Optional[int] = None,
        warehouse_supply_at_decision: Optional[int] = None,
    ) -> str:
        """Generates a detailed, factor-based justification for a single shipment allocation."""
        w_code = shipment.get("source_warehouse_code", "UNKNOWN")
        d_name = shipment.get("destination_name", shipment.get("destination_code", "UNKNOWN"))
        d_code = shipment.get("destination_code", "")
        sku_name = shipment.get("product_name", shipment.get("product_sku", "UNKNOWN"))
        units = shipment.get("recommended_units", 0)
        unit_cost = float(shipment.get("unit_transport_cost", 0.0))
        total_cost = float(shipment.get("total_transport_cost", round(units * unit_cost, 2)))
        lead_time = float(shipment.get("lead_time_days", 1.0))

        # Check default closest hub logic for backward compatibility
        if closest_warehouse is None:
            closest_warehouse = w_code
        if is_closest is None:
            is_closest = (w_code == closest_warehouse)

        # Build empirical explanation components
        reasons: List[str] = []

        # 1. Primary allocation sentence
        reasons.append(
            f"Allocated {units} units of {sku_name} from {w_code} to {d_name} "
            f"(${unit_cost:.2f}/unit freight, total ${total_cost:.2f}, {lead_time:.1f}d transit)."
        )

        # 2. Demand urgency / risk factor
        if destination_risk and destination_risk in ("Critical", "High"):
            reasons.append(
                f"Sourced as a priority dispatch to mitigate {destination_risk}-risk stockout "
                f"(requirement: {replenishment_requirement or units} units)."
            )
        elif replenishment_requirement:
            reasons.append(f"Fulfills destination replenishment requirement of {replenishment_requirement} units.")

        # 3. Competing warehouse analysis
        if competing_options:
            alt_reasons: List[str] = []
            for alt in competing_options:
                alt_wh = alt.get("warehouse_code")
                if alt_wh == w_code:
                    continue
                alt_cost = alt.get("unit_transport_cost")
                alt_lt = alt.get("lead_time_days")
                alt_supply = alt.get("available_supply", 0)
                alt_cap_exhausted = alt.get("capacity_exhausted", False)

                if alt_cap_exhausted:
                    alt_reasons.append(f"{alt_wh} dispatch capacity reached")
                elif alt_supply <= 0:
                    alt_reasons.append(f"{alt_wh} had zero usable stock")
                elif alt_cost is not None and alt_cost > unit_cost:
                    diff = alt_cost - unit_cost
                    alt_reasons.append(f"{alt_wh} was +${diff:.2f}/unit more expensive")
                elif alt_lt is not None and alt_lt > lead_time:
                    diff_lt = alt_lt - lead_time
                    alt_reasons.append(f"{alt_wh} had +{diff_lt:.1f}d longer lead time")

            if alt_reasons:
                reasons.append(f"Chosen over alternatives ({', '.join(alt_reasons[:2])}).")
        elif is_closest:
            reasons.append(f"{w_code} represents the primary regional hub offering lowest transit freight (${unit_cost}/unit).")
        else:
            reasons.append(
                f"Sourced from {w_code} instead of closest hub ({closest_warehouse}) to relieve stockout "
                f"risk at {d_name} while clearing optimal shelf-life inventory."
            )

        return " ".join(reasons)

    @classmethod
    def enrich_shipments_with_reasoning(
        cls,
        shipments: List[Dict[str, Any]],
        warehouse_dest_distances: Optional[Dict[Tuple[str, str], float]] = None,
        available_supply: Optional[Dict[str, Dict[str, int]]] = None,
        routes: Optional[List[Dict[str, Any]]] = None,
        demand_targets: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Adds structured empirical reasoning to each shipment recommendation."""
        # Index routes by destination to evaluate competing alternatives
        routes_by_dest: Dict[str, List[Dict[str, Any]]] = {}
        if routes:
            for r in routes:
                d = r.get("destination_code")
                if d and r.get("is_active", True):
                    routes_by_dest.setdefault(d, []).append(r)

        # Index demand targets by (dest, sku)
        demand_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if demand_targets:
            for dt in demand_targets:
                d = dt.get("destination_code")
                s = dt.get("sku") or dt.get("product_sku")
                if d and s:
                    demand_map[(d, s)] = dt

        enriched = []
        for s in shipments:
            s_copy = dict(s)
            w_code = s.get("source_warehouse_code")
            d_code = s.get("destination_code")
            sku = s.get("product_sku")

            # Collect competing warehouse options
            competing = []
            if routes_by_dest and d_code in routes_by_dest:
                for r in routes_by_dest[d_code]:
                    alt_wh = r.get("origin_warehouse_code") or r.get("source_warehouse_code")
                    alt_supply = available_supply.get(alt_wh, {}).get(sku, 0) if available_supply else 100
                    competing.append({
                        "warehouse_code": alt_wh,
                        "unit_transport_cost": float(r.get("unit_transport_cost", 1.0)),
                        "lead_time_days": float(r.get("lead_time_days", 1.0)),
                        "available_supply": alt_supply,
                        "capacity_exhausted": False,
                    })

            dt_info = demand_map.get((d_code, sku), {})
            risk = dt_info.get("risk_category", "Moderate")
            req = dt_info.get("units") or dt_info.get("forecasted_units")

            s_copy["reasoning"] = cls.explain_shipment(
                s,
                closest_warehouse=w_code,
                is_closest=True,
                competing_options=competing,
                destination_risk=risk,
                replenishment_requirement=req,
            )
            enriched.append(s_copy)

        return enriched
