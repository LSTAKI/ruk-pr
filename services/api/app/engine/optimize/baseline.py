"""
Deterministic, Constraint-Aware Greedy Baseline Heuristic
==========================================================

Provides an independent benchmark for the OR-Tools optimization engine.
Enforces the exact same physical constraints:
  - Warehouse usable supply bounds (excluding reserved, expired, quarantined).
  - Demand requirement upper bounds (no over-allocation).
  - Active route eligibility (inactive routes rejected).
  - Maximum delivery lead-time cutoff.
  - Warehouse daily dispatch throughput capacities.
  - Destination daily receiving throughput capacities.
  - Integer shipment quantities.

The baseline prioritizes urgent demand requirements and selects the lowest-cost
eligible warehouse with available supply and capacity.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple


def _risk_priority(risk_category: str) -> int:
    return {
        "Critical": 4,
        "High": 3,
        "Moderate": 2,
        "Low": 1,
        "InsufficientData": 0,
    }.get(risk_category, 1)


def solve_greedy_baseline(
    warehouses: List[Dict[str, Any]],
    destinations: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    available_supply: Dict[str, Dict[str, int]],
    demand_targets: List[Dict[str, Any]],
    routes: Optional[List[Dict[str, Any]]] = None,
    max_lead_time_days: Optional[float] = None,
) -> Dict[str, Any]:
    """Computes a deterministic, constraint-aware greedy allocation plan.

    Parameters
    ----------
    warehouses:
        List of warehouse records with 'code' and optional 'daily_dispatch_capacity_units'.
    destinations:
        List of destination records with 'code' and optional 'daily_receiving_capacity_units'.
    products:
        List of product records with 'sku'.
    available_supply:
        Mapping of {wh_code: {sku: usable_units}}.
    demand_targets:
        List of dicts with 'destination_code', 'sku', 'units' (or 'forecasted_units'),
        and optional 'risk_category'.
    routes:
        List of route records with 'origin_warehouse_code', 'destination_code',
        'unit_transport_cost', 'lead_time_days', and 'is_active'.
    max_lead_time_days:
        Optional lead-time threshold. Routes exceeding this are excluded.

    Returns
    -------
    Dict containing baseline shipments, total_units, total_cost, unmet units, and fulfillment rate.
    """
    start_time = time.perf_counter()

    # 1. Capacity tracking
    wh_dispatch_rem: Dict[str, int] = {}
    for w in warehouses:
        cap = w.get("daily_dispatch_capacity_units")
        wh_dispatch_rem[w["code"]] = cap if (cap is not None and cap > 0) else 10**9

    dst_recv_rem: Dict[str, int] = {}
    for d in destinations:
        cap = d.get("daily_receiving_capacity_units")
        dst_recv_rem[d["code"]] = cap if (cap is not None and cap > 0) else 10**9

    wh_supply_rem: Dict[str, Dict[str, int]] = {
        w_code: dict(skus) for w_code, skus in available_supply.items()
    }

    # 2. Index active, eligible routes: (wh_code, dest_code) -> route_dict
    route_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if routes:
        for r in routes:
            w_code = r.get("origin_warehouse_code") or r.get("source_warehouse_code")
            d_code = r.get("destination_code")
            if not w_code or not d_code:
                continue
            if not r.get("is_active", True):
                continue
            lt = float(r.get("lead_time_days", 1.0))
            if max_lead_time_days is not None and lt > max_lead_time_days:
                continue
            route_map[(w_code, d_code)] = r

    # 3. Normalize demand targets and sort by priority
    normalized_demands = []
    total_demand_units = 0
    for dt in demand_targets:
        d_code = dt.get("destination_code")
        sku = dt.get("sku") or dt.get("product_sku")
        req_units = int(dt.get("units") if "units" in dt else dt.get("forecasted_units", 0))
        if req_units <= 0:
            continue
        risk = dt.get("risk_category", "Moderate")
        total_demand_units += req_units
        normalized_demands.append({
            "destination_code": d_code,
            "sku": sku,
            "units": req_units,
            "risk_category": risk,
            "destination_name": dt.get("destination_name", d_code),
            "product_name": dt.get("product_name", sku),
        })

    # Sort: highest risk urgency first, then highest demand quantity
    normalized_demands.sort(
        key=lambda d: (-_risk_priority(d["risk_category"]), -d["units"], d["destination_code"])
    )

    # 4. Greedy allocation
    shipments: List[Dict[str, Any]] = []
    total_transport_cost = 0.0
    total_fulfilled_units = 0
    unmet_demand_list: List[Dict[str, Any]] = []

    dest_codes = {d["code"] for d in destinations}
    wh_codes = [w["code"] for w in warehouses]

    for req in normalized_demands:
        d_code = req["destination_code"]
        sku = req["sku"]
        needed = req["units"]
        fulfilled_for_req = 0

        # Find eligible candidate warehouses with available supply and capacity
        candidates: List[Tuple[float, float, str, Dict[str, Any]]] = []
        for w_code in wh_codes:
            # Check route eligibility
            if routes is not None and (w_code, d_code) not in route_map:
                continue

            r_info = route_map.get((w_code, d_code), {})
            cost = float(r_info.get("unit_transport_cost", 1.0))
            lt = float(r_info.get("lead_time_days", 1.0))

            avail_supply = wh_supply_rem.get(w_code, {}).get(sku, 0)
            avail_dispatch = wh_dispatch_rem.get(w_code, 0)
            avail_recv = dst_recv_rem.get(d_code, 0)

            if avail_supply > 0 and avail_dispatch > 0 and avail_recv > 0:
                # Rank by unit cost asc, then lead time asc
                candidates.append((cost, lt, w_code, r_info))

        candidates.sort(key=lambda c: (c[0], c[1], c[2]))

        for cost, lt, w_code, r_info in candidates:
            if needed <= 0:
                break

            avail_supply = wh_supply_rem[w_code].get(sku, 0)
            avail_dispatch = wh_dispatch_rem[w_code]
            avail_recv = dst_recv_rem[d_code]

            alloc = min(needed, avail_supply, avail_dispatch, avail_recv)
            if alloc > 0:
                shipment_cost = round(alloc * cost, 2)
                shipments.append({
                    "source_warehouse_code": w_code,
                    "destination_code": d_code,
                    "destination_name": req["destination_name"],
                    "product_sku": sku,
                    "product_name": req["product_name"],
                    "recommended_units": alloc,
                    "unit_transport_cost": cost,
                    "total_transport_cost": shipment_cost,
                    "lead_time_days": lt,
                    "estimated_expiry_risk_pct": 0.0,
                    "allocation_method": "greedy_baseline",
                })

                wh_supply_rem[w_code][sku] -= alloc
                wh_dispatch_rem[w_code] -= alloc
                dst_recv_rem[d_code] -= alloc
                needed -= alloc
                fulfilled_for_req += alloc
                total_fulfilled_units += alloc
                total_transport_cost += shipment_cost

        unmet = req["units"] - fulfilled_for_req
        if unmet > 0:
            unmet_demand_list.append({
                "destination_code": d_code,
                "destination_name": req["destination_name"],
                "product_sku": sku,
                "product_name": req["product_name"],
                "demanded_units": req["units"],
                "fulfilled_units": fulfilled_for_req,
                "unmet_units": unmet,
                "risk_category": req["risk_category"],
            })

    elapsed = round(time.perf_counter() - start_time, 4)
    fulfillment_rate = (
        round(total_fulfilled_units / total_demand_units, 4) if total_demand_units > 0 else 1.0
    )

    return {
        "method": "greedy_baseline",
        "solver_status": "FEASIBLE" if total_fulfilled_units > 0 or total_demand_units == 0 else "NO_FEASIBLE_SHIPMENT",
        "total_units": total_fulfilled_units,
        "total_transport_cost": round(total_transport_cost, 2),
        "total_demand_units": total_demand_units,
        "total_unmet_units": total_demand_units - total_fulfilled_units,
        "fulfillment_rate": fulfillment_rate,
        "runtime_seconds": elapsed,
        "shipments": shipments,
        "unmet_demands": unmet_demand_list,
    }
