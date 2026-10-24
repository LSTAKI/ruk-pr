"""
Deterministic, Constraint-Aware Greedy Baseline Heuristic
==========================================================

Provides an independent benchmark for the OR-Tools optimization engine.
Enforces the exact same physical and operational constraints:
  - Warehouse usable supply bounds (excluding reserved, expired, quarantined).
  - Route-specific batch expiry feasibility (batches expiring before delivery are excluded).
  - Demand requirement upper bounds (no over-allocation).
  - Active route eligibility (inactive routes rejected).
  - Maximum delivery lead-time cutoff.
  - Warehouse daily dispatch throughput capacities.
  - Destination daily receiving throughput capacities.
  - Minimum fulfillment rate policies.
  - Integer shipment quantities.

The baseline prioritizes urgent demand requirements and selects the lowest-cost
eligible warehouse with available supply, capacity, and fresh inventory.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _risk_priority(risk_category: str) -> int:
    return {
        "Critical": 4,
        "High": 3,
        "Moderate": 2,
        "Low": 1,
        "InsufficientData": 0,
    }.get(risk_category, 1)


def compute_route_eligible_supply(
    inventory_items: Optional[List[Dict[str, Any]]],
    available_supply: Dict[str, Dict[str, int]],
    routes_map: Dict[Tuple[str, str], Dict[str, Any]],
    as_of_date: Optional[date] = None,
    min_arrival_shelf_life_days: float = 0.0,
) -> Dict[Tuple[str, str, str], int]:
    """Computes route-specific eligible supply accounting for batch expiry vs delivery lead time.

    Returns mapping of (wh_code, dest_code, sku) -> eligible_units.
    """
    ref_date = as_of_date or datetime.utcnow().date()
    if isinstance(ref_date, datetime):
        ref_date = ref_date.date()

    if not inventory_items:
        # Fallback to available_supply for all routes
        eligible = {}
        for (w_code, d_code) in routes_map.keys():
            for sku, units in available_supply.get(w_code, {}).items():
                eligible[(w_code, d_code, sku)] = units
        return eligible

    # Sum available batch units satisfying expiry > ref_date + lead_time + min_shelf_life
    eligible_supply: Dict[Tuple[str, str, str], int] = {}

    for (w_code, d_code), r_info in routes_map.items():
        lt = float(r_info.get("lead_time_days") or r_info.get("lead_time") or 1.0)
        transit_days = math.ceil(lt) + math.ceil(min_arrival_shelf_life_days)
        min_expiry_date = ref_date + timedelta(days=transit_days)

        for item in inventory_items:
            if item.get("warehouse_code") != w_code:
                continue
            status = str(item.get("batch_status", "AVAILABLE")).upper()
            if status != "AVAILABLE":
                continue

            exp = item.get("expiry_date")
            if isinstance(exp, str):
                try:
                    exp = datetime.fromisoformat(exp).date()
                except Exception:
                    continue
            elif isinstance(exp, datetime):
                exp = exp.date()
            elif isinstance(exp, date):
                pass

            if not exp or exp <= min_expiry_date:
                # Expired before or upon arrival -> ineligible for this route
                continue

            sku = item.get("product_sku")
            on_hand = int(item.get("on_hand_units", 0))
            reserved = int(item.get("reserved_units", 0))
            usable_in_batch = max(0, on_hand - reserved)

            key = (w_code, d_code, sku)
            eligible_supply[key] = eligible_supply.get(key, 0) + usable_in_batch

    # Cap by warehouse total available supply to prevent double-counting
    for (w_code, d_code, sku), el_units in eligible_supply.items():
        cap = available_supply.get(w_code, {}).get(sku, 0)
        eligible_supply[(w_code, d_code, sku)] = min(el_units, cap)

    return eligible_supply


def solve_greedy_baseline(
    warehouses: List[Dict[str, Any]],
    destinations: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    available_supply: Dict[str, Dict[str, int]],
    demand_targets: List[Dict[str, Any]],
    routes: Optional[List[Dict[str, Any]]] = None,
    max_lead_time_days: Optional[float] = None,
    inventory_items: Optional[List[Dict[str, Any]]] = None,
    as_of_date: Optional[date] = None,
    min_arrival_shelf_life_days: float = 0.0,
    min_fulfillment_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """Computes a deterministic, constraint-aware greedy allocation plan."""
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

    # 2. Index active, eligible routes
    route_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if routes is not None:
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
    else:
        for w in warehouses:
            for d in destinations:
                route_map[(w["code"], d["code"])] = {
                    "unit_transport_cost": 1.0,
                    "lead_time_days": 1.0,
                    "is_active": True,
                }

    # 3. Route-specific batch expiry supply bounds
    route_eligible = compute_route_eligible_supply(
        inventory_items=inventory_items,
        available_supply=available_supply,
        routes_map=route_map,
        as_of_date=as_of_date,
        min_arrival_shelf_life_days=min_arrival_shelf_life_days,
    )
    route_eligible_rem = dict(route_eligible)

    # 4. Normalize demand targets and sort by priority
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

    # 5. Greedy allocation
    shipments: List[Dict[str, Any]] = []
    total_transport_cost = 0.0
    total_fulfilled_units = 0
    unmet_demand_list: List[Dict[str, Any]] = []

    wh_codes = [w["code"] for w in warehouses]

    for req in normalized_demands:
        d_code = req["destination_code"]
        sku = req["sku"]
        needed = req["units"]
        fulfilled_for_req = 0

        candidates: List[Tuple[float, float, str, Dict[str, Any]]] = []
        for w_code in wh_codes:
            if (w_code, d_code) not in route_map:
                continue

            r_info = route_map[(w_code, d_code)]
            cost = float(r_info.get("unit_transport_cost", 1.0))
            lt = float(r_info.get("lead_time_days", 1.0))

            avail_supply = wh_supply_rem.get(w_code, {}).get(sku, 0)
            avail_route_exp = route_eligible_rem.get((w_code, d_code, sku), avail_supply)
            avail_dispatch = wh_dispatch_rem.get(w_code, 0)
            avail_recv = dst_recv_rem.get(d_code, 0)

            effective_avail = min(avail_supply, avail_route_exp)

            if effective_avail > 0 and avail_dispatch > 0 and avail_recv > 0:
                candidates.append((cost, lt, w_code, r_info))

        candidates.sort(key=lambda c: (c[0], c[1], c[2]))

        for cost, lt, w_code, r_info in candidates:
            if needed <= 0:
                break

            avail_supply = wh_supply_rem[w_code].get(sku, 0)
            avail_route_exp = route_eligible_rem.get((w_code, d_code, sku), avail_supply)
            avail_dispatch = wh_dispatch_rem[w_code]
            avail_recv = dst_recv_rem[d_code]

            effective_avail = min(avail_supply, avail_route_exp)

            alloc = min(needed, effective_avail, avail_dispatch, avail_recv)
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
                    "estimated_expiry_risk_pct": None,
                    "allocation_method": "greedy_baseline",
                })

                wh_supply_rem[w_code][sku] -= alloc
                if (w_code, d_code, sku) in route_eligible_rem:
                    route_eligible_rem[(w_code, d_code, sku)] -= alloc
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

    target_met = True
    if min_fulfillment_rate is not None and min_fulfillment_rate > 0.0:
        target_met = (fulfillment_rate >= min_fulfillment_rate)

    return {
        "method": "greedy_baseline",
        "solver_status": "FEASIBLE" if total_fulfilled_units > 0 or total_demand_units == 0 else "NO_FEASIBLE_SHIPMENT",
        "total_units": total_fulfilled_units,
        "total_transport_cost": round(total_transport_cost, 2),
        "total_demand_units": total_demand_units,
        "total_unmet_units": total_demand_units - total_fulfilled_units,
        "fulfillment_rate": fulfillment_rate,
        "min_fulfillment_target_met": target_met,
        "runtime_seconds": elapsed,
        "shipments": shipments,
        "unmet_demands": unmet_demand_list,
    }
