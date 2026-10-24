"""
Constraint-Aware Distribution Optimization Solver
=================================================

Formulates and solves the FMCG multi-warehouse, multi-product, multi-destination
allocation problem using Google OR-Tools Mixed-Integer Programming (MIP).

Core Capabilities:
-----------------
  1. Exact Integer Optimization: Native integer variables (x >= 0, integer).
  2. Multi-Profile Formulations:
     - Cost-First: Minimizes transportation freight cost subject to a configurable
       minimum fulfillment rate policy (default 80%). Unconstrained mode requires
       explicit opt-in with documented trade-off warnings.
     - Service-First: Lexicographic two-stage optimization (Stage 1: maximize fulfillment;
       Stage 2: minimize freight cost at optimal fulfillment).
     - Balanced: Multi-objective blending freight cost ($/unit), lost-sales shortage penalty
       ($/unit), and transit delay cost ($/day/unit * days = $/unit) with consistent units.
  3. Comprehensive Physical & Operational Constraints:
     - Warehouse-product usable supply bounds (excluding reserved, expired, quarantined).
     - Route-specific batch expiry feasibility (batches expiring before delivery are excluded).
     - Destination-product demand bounds (strict equality with explicit unmet demand variables).
     - Active route eligibility (inactive or missing routes rejected).
     - Maximum delivery lead-time cutoffs.
     - Warehouse daily dispatch throughput capacities.
     - Destination daily receiving throughput capacities.
  4. Real Route Costs: Consumes empirical Route table freight rates and lead times,
     with distance fallback for legacy unit tests.
  5. Deterministic Greedy Baseline Comparison: Directly compares OR-Tools MIP results
     against the constraint-aware greedy baseline on the exact same inputs.
  6. Batch-Level Freshness Enforcement: Verifies batches arrive with required shelf life.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from ortools.linear_solver import pywraplp

from app.engine.optimize.baseline import compute_route_eligible_supply, solve_greedy_baseline


def calculate_geo_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two GPS coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


class DistributionSolver:
    """MIP optimization solver using Google OR-Tools (SCIP / CBC / GLOP)."""

    def __init__(
        self,
        transport_weight: float = 1.0,
        stockout_penalty_weight: float = 5.0,
        expiry_risk_weight: float = 2.5,
        lead_time_penalty_weight: float = 0.20,
        min_fulfillment_rate: Optional[float] = 0.80,
        allow_unconstrained_cost_first: bool = False,
        min_arrival_shelf_life_days: float = 0.0,
        max_solver_time_seconds: int = 10,
        profile: str = "balanced",  # "cost_first", "service_first", "balanced"
        max_lead_time_days: Optional[float] = None,
    ):
        if transport_weight < 0.0:
            raise ValueError("transport_weight must be non-negative.")
        if stockout_penalty_weight < 0.0:
            raise ValueError("stockout_penalty_weight must be non-negative.")
        if expiry_risk_weight < 0.0:
            raise ValueError("expiry_risk_weight must be non-negative.")
        if lead_time_penalty_weight < 0.0:
            raise ValueError("lead_time_penalty_weight must be non-negative.")
        if min_fulfillment_rate is not None and not (0.0 <= min_fulfillment_rate <= 1.0):
            raise ValueError("min_fulfillment_rate must be between 0.0 and 1.0.")

        self.transport_weight = transport_weight
        self.stockout_penalty_weight = stockout_penalty_weight
        self.expiry_risk_weight = expiry_risk_weight
        self.lead_time_penalty_weight = lead_time_penalty_weight
        self.min_fulfillment_rate = min_fulfillment_rate
        self.allow_unconstrained_cost_first = allow_unconstrained_cost_first
        self.min_arrival_shelf_life_days = min_arrival_shelf_life_days
        self.max_solver_time_seconds = max_solver_time_seconds
        self.profile = profile.lower() if profile else "balanced"
        self.max_lead_time_days = max_lead_time_days

    def solve_distribution_plan(
        self,
        warehouses: List[Dict[str, Any]],
        destinations: List[Dict[str, Any]],
        products: List[Dict[str, Any]],
        available_supply: Dict[str, Dict[str, int]],
        demand_targets: List[Dict[str, Any]],
        routes: Optional[List[Dict[str, Any]]] = None,
        inventory_items: Optional[List[Dict[str, Any]]] = None,
        profile: Optional[str] = None,
        max_lead_time_days: Optional[float] = None,
        as_of_date: Optional[date] = None,
        min_fulfillment_rate: Optional[float] = None,
        allow_unconstrained_cost_first: Optional[bool] = None,
        lead_time_penalty_weight: Optional[float] = None,
        min_arrival_shelf_life_days: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Formulates and solves the distribution planning problem."""
        start_time = time.perf_counter()
        opt_profile = (profile or self.profile).lower()
        lead_time_cutoff = max_lead_time_days if max_lead_time_days is not None else self.max_lead_time_days

        eff_min_fulfillment = (
            min_fulfillment_rate
            if min_fulfillment_rate is not None
            else self.min_fulfillment_rate
        )
        eff_allow_unconstrained = (
            allow_unconstrained_cost_first
            if allow_unconstrained_cost_first is not None
            else self.allow_unconstrained_cost_first
        )
        eff_lt_penalty = (
            lead_time_penalty_weight
            if lead_time_penalty_weight is not None
            else self.lead_time_penalty_weight
        )
        eff_min_shelf_life = (
            min_arrival_shelf_life_days
            if min_arrival_shelf_life_days is not None
            else self.min_arrival_shelf_life_days
        )

        warnings: List[str] = []

        # ------------------------------------------------------------------
        # 1. Input Validation
        # ------------------------------------------------------------------
        if not warehouses or not destinations or not products:
            return {
                "solver_status": "INVALID_INPUT",
                "status_message": "Warehouses, destinations, and products lists must not be empty.",
                "total_transport_cost": 0.0,
                "total_units": 0,
                "shipments": [],
                "unmet_demands": [],
                "warnings": ["INVALID_INPUT: empty entity collections"],
                "solver_runtime_seconds": 0.0,
            }

        # ------------------------------------------------------------------
        # 2. Build Route Lookup & Costs
        # ------------------------------------------------------------------
        route_info: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if routes is not None:
            for r in routes:
                w_code = r.get("origin_warehouse_code") or r.get("source_warehouse_code")
                d_code = r.get("destination_code")
                if not w_code or not d_code:
                    continue
                if not r.get("is_active", True):
                    continue
                lt = float(r.get("lead_time_days", 1.0))
                if lead_time_cutoff is not None and lt > lead_time_cutoff:
                    continue
                route_info[(w_code, d_code)] = {
                    "cost": float(r.get("unit_transport_cost", 1.0)),
                    "lead_time": lt,
                    "lead_time_days": lt,
                    "is_active": True,
                }
        else:
            # Distance-based fallback for tests that don't pass routes
            for w in warehouses:
                for d in destinations:
                    lat1, lon1 = w.get("latitude", 0.0), w.get("longitude", 0.0)
                    lat2, lon2 = d.get("latitude", 0.0), d.get("longitude", 0.0)
                    dist = calculate_geo_distance_km(lat1, lon1, lat2, lon2)
                    cost = max(0.50, round(dist * 0.0015, 3))
                    lt_est = max(1.0, round(dist / 500.0, 1))
                    route_info[(w["code"], d["code"])] = {
                        "cost": cost,
                        "lead_time": lt_est,
                        "lead_time_days": lt_est,
                        "is_active": True,
                    }

        # ------------------------------------------------------------------
        # 3. Route-Specific Batch Expiry Bounds
        # ------------------------------------------------------------------
        route_eligible_supply = compute_route_eligible_supply(
            inventory_items=inventory_items,
            available_supply=available_supply,
            routes_map=route_info,
            as_of_date=as_of_date,
            min_arrival_shelf_life_days=eff_min_shelf_life,
        )

        # ------------------------------------------------------------------
        # 4. Check Demand and Fulfillment Feasibility
        # ------------------------------------------------------------------
        wh_codes = [w["code"] for w in warehouses]
        dest_codes = [d["code"] for d in destinations]
        product_skus = [p["sku"] for p in products]

        prod_meta: Dict[str, Dict[str, Any]] = {p["sku"]: p for p in products}
        wh_meta: Dict[str, Dict[str, Any]] = {w["code"]: w for w in warehouses}
        dest_meta: Dict[str, Dict[str, Any]] = {d["code"]: d for d in destinations}

        demand_map: Dict[Tuple[str, str], int] = {}
        risk_map: Dict[Tuple[str, str], str] = {}
        total_demanded_units = 0

        for dt in demand_targets:
            d_code = dt.get("destination_code")
            sku = dt.get("sku") or dt.get("product_sku")
            units = int(dt.get("units") if "units" in dt else dt.get("forecasted_units", 0))
            if d_code and sku:
                dem = max(0, units)
                demand_map[(d_code, sku)] = dem
                risk_map[(d_code, sku)] = dt.get("risk_category", "Moderate")
                total_demanded_units += dem

        total_network_supply = sum(
            sum(skus.values()) for skus in available_supply.values()
        )

        # Cost-First fulfillment target check
        target_units = 0
        if opt_profile == "cost_first":
            if not eff_allow_unconstrained and eff_min_fulfillment is not None and eff_min_fulfillment > 0.0:
                target_units = math.ceil(eff_min_fulfillment * total_demanded_units)
                if total_network_supply < target_units:
                    msg = (
                        f"Infeasible fulfillment target under Cost-First: Requested "
                        f"{eff_min_fulfillment*100:.1f}% ({target_units} units) cannot be met "
                        f"because total network usable supply is only {total_network_supply} units."
                    )
                    return self._build_empty_result(
                        solver_status="TARGET_UNACHIEVABLE",
                        status_message=msg,
                        demand_map=demand_map,
                        prod_meta=prod_meta,
                        dest_meta=dest_meta,
                        start_time=start_time,
                        warnings=[msg],
                    )
            elif eff_allow_unconstrained or eff_min_fulfillment == 0.0:
                warnings.append(
                    "Unconstrained cost-first policy active: demand may be left unmet if unit "
                    "transport cost exceeds lost-sales penalties."
                )

        # ------------------------------------------------------------------
        # 5. Create OR-Tools MIP Solver
        # ------------------------------------------------------------------
        solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            solver = pywraplp.Solver.CreateSolver("CBC")
        if not solver:
            solver = pywraplp.Solver.CreateSolver("GLOP")

        if not solver:
            return {
                "solver_status": "INTERNAL_ERROR",
                "status_message": "No linear/integer solver engine available in OR-Tools.",
                "total_transport_cost": 0.0,
                "total_units": 0,
                "shipments": [],
                "unmet_demands": [],
                "warnings": ["INTERNAL_ERROR: solver backend unavailable"],
                "solver_runtime_seconds": 0.0,
            }

        solver.SetTimeLimit(self.max_solver_time_seconds * 1000)

        # ------------------------------------------------------------------
        # 6. Decision Variables
        # ------------------------------------------------------------------
        x: Dict[Tuple[str, str, str], Any] = {}
        u: Dict[Tuple[str, str], Any] = {}

        for w_code in wh_codes:
            for d_code in dest_codes:
                if (w_code, d_code) not in route_info:
                    continue  # Inactive or missing route
                for sku in product_skus:
                    dem = demand_map.get((d_code, sku), 0)
                    sup = available_supply.get(w_code, {}).get(sku, 0)
                    exp_sup = route_eligible_supply.get((w_code, d_code, sku), sup)
                    ub = min(dem, sup, exp_sup)
                    var_name = f"x_{w_code}_{d_code}_{sku}"
                    if solver.IsMip():
                        x[(w_code, d_code, sku)] = solver.IntVar(0, max(0, ub), var_name)
                    else:
                        x[(w_code, d_code, sku)] = solver.NumVar(0.0, float(max(0, ub)), var_name)

        for d_code in dest_codes:
            for sku in product_skus:
                dem = demand_map.get((d_code, sku), 0)
                var_name = f"u_{d_code}_{sku}"
                if solver.IsMip():
                    u[(d_code, sku)] = solver.IntVar(0, dem, var_name)
                else:
                    u[(d_code, sku)] = solver.NumVar(0.0, float(dem), var_name)

        # ------------------------------------------------------------------
        # 7. Constraints
        # ------------------------------------------------------------------
        # Constraint A: Warehouse supply limit
        for w_code in wh_codes:
            for sku in product_skus:
                avail = available_supply.get(w_code, {}).get(sku, 0)
                eligible_vars = [
                    x[(w_code, d_code, sku)]
                    for d_code in dest_codes
                    if (w_code, d_code, sku) in x
                ]
                if eligible_vars:
                    solver.Add(
                        solver.Sum(eligible_vars) <= float(avail),
                        f"supply_{w_code}_{sku}",
                    )

        # Constraint B: Route-specific batch expiry supply limit
        for (w_code, d_code, sku), x_var in x.items():
            exp_avail = route_eligible_supply.get((w_code, d_code, sku))
            if exp_avail is not None:
                solver.Add(x_var <= float(exp_avail), f"expiry_{w_code}_{d_code}_{sku}")

        # Constraint C: Exact demand balance: sum_w(x) + u == Demand
        for d_code in dest_codes:
            for sku in product_skus:
                dem = demand_map.get((d_code, sku), 0)
                eligible_vars = [
                    x[(w_code, d_code, sku)]
                    for w_code in wh_codes
                    if (w_code, d_code, sku) in x
                ]
                u_var = u[(d_code, sku)]
                if eligible_vars:
                    solver.Add(
                        solver.Sum(eligible_vars) + u_var == float(dem),
                        f"demand_balance_{d_code}_{sku}",
                    )
                else:
                    solver.Add(u_var == float(dem), f"demand_unmet_no_route_{d_code}_{sku}")

        # Constraint D: Warehouse daily dispatch throughput limit
        for w_code in wh_codes:
            disp_cap = wh_meta.get(w_code, {}).get("daily_dispatch_capacity_units")
            if disp_cap is not None and disp_cap > 0:
                wh_vars = [
                    x[(w_code, d_code, sku)]
                    for d_code in dest_codes
                    for sku in product_skus
                    if (w_code, d_code, sku) in x
                ]
                if wh_vars:
                    solver.Add(
                        solver.Sum(wh_vars) <= float(disp_cap),
                        f"dispatch_cap_{w_code}",
                    )

        # Constraint E: Destination daily receiving throughput limit
        for d_code in dest_codes:
            recv_cap = dest_meta.get(d_code, {}).get("daily_receiving_capacity_units")
            if recv_cap is not None and recv_cap > 0:
                dst_vars = [
                    x[(w_code, d_code, sku)]
                    for w_code in wh_codes
                    for sku in product_skus
                    if (w_code, d_code, sku) in x
                ]
                if dst_vars:
                    solver.Add(
                        solver.Sum(dst_vars) <= float(recv_cap),
                        f"receiving_cap_{d_code}",
                    )

        # Constraint F: Minimum fulfillment rate for Cost-First (when policy enabled)
        if opt_profile == "cost_first" and target_units > 0:
            if x:
                solver.Add(
                    solver.Sum(list(x.values())) >= float(target_units),
                    "cost_first_min_fulfillment_floor",
                )

        # ------------------------------------------------------------------
        # 8. Objective Function Formulation
        # ------------------------------------------------------------------
        objective = solver.Objective()

        if opt_profile == "service_first":
            # Lexicographic Stage 1: Maximize fulfillment (minimize total unmet demand)
            for (d_code, sku), u_var in u.items():
                objective.SetCoefficient(u_var, 1.0)
            objective.SetMinimization()

            stage1_status = solver.Solve()
            if stage1_status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
                return self._build_empty_result(
                    solver_status="INFEASIBLE",
                    status_message="Service-First stage 1 (fulfillment maximization) found no feasible solution.",
                    demand_map=demand_map,
                    prod_meta=prod_meta,
                    dest_meta=dest_meta,
                    start_time=start_time,
                )

            min_unmet = sum(int(round(u_var.solution_value())) for u_var in u.values())

            # Stage 2: Lock fulfillment at optimum, minimize transportation freight
            solver.Add(
                solver.Sum(list(u.values())) <= float(min_unmet),
                "stage2_fulfillment_lock",
            )

            objective.Clear()
            for (w_code, d_code, sku), x_var in x.items():
                cost = route_info[(w_code, d_code)]["cost"] * self.transport_weight
                objective.SetCoefficient(x_var, cost)
            objective.SetMinimization()

        elif opt_profile == "cost_first":
            # Cost-First: Minimize freight costs subject to fulfillment floor
            for (w_code, d_code, sku), x_var in x.items():
                cost = route_info[(w_code, d_code)]["cost"] * self.transport_weight
                objective.SetCoefficient(x_var, cost)

            for (d_code, sku), u_var in u.items():
                lost_penalty = float(prod_meta.get(sku, {}).get("lost_sales_penalty", 5.0))
                penalty = lost_penalty * 2.0
                objective.SetCoefficient(u_var, penalty)

            objective.SetMinimization()

        else:
            # Balanced: Multi-objective blending freight cost, transit speed, and lost-sales penalties
            # Units: all terms are expressed in $/unit!
            #   freight: cost * transport_weight ($/unit)
            #   lead time: lead_time_days * lead_time_penalty_weight (days * $/day/unit = $/unit)
            #   unmet: lost_sales_penalty * stockout_penalty_weight ($/unit)
            for (w_code, d_code, sku), x_var in x.items():
                freight_cost = route_info[(w_code, d_code)]["cost"] * self.transport_weight
                lt_cost = route_info[(w_code, d_code)]["lead_time"] * eff_lt_penalty
                objective.SetCoefficient(x_var, freight_cost + lt_cost)

            for (d_code, sku), u_var in u.items():
                lost_penalty = float(prod_meta.get(sku, {}).get("lost_sales_penalty", 5.0))
                shortage_cost = lost_penalty * self.stockout_penalty_weight
                objective.SetCoefficient(u_var, shortage_cost)

            objective.SetMinimization()

        # ------------------------------------------------------------------
        # 9. Solve
        # ------------------------------------------------------------------
        status_code = solver.Solve()
        status_map = {
            pywraplp.Solver.OPTIMAL: "OPTIMAL",
            pywraplp.Solver.FEASIBLE: "FEASIBLE",
            pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
            pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
            pywraplp.Solver.ABNORMAL: "ABNORMAL",
            pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
        }
        status_str = status_map.get(status_code, "UNKNOWN")

        if status_code not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return self._build_empty_result(
                solver_status=status_str,
                status_message=f"Solver terminated with status {status_str}.",
                demand_map=demand_map,
                prod_meta=prod_meta,
                dest_meta=dest_meta,
                start_time=start_time,
                warnings=warnings,
            )

        # ------------------------------------------------------------------
        # 10. Extract Shipment Recommendations
        # ------------------------------------------------------------------
        shipments: List[Dict[str, Any]] = []
        total_transport_cost = 0.0
        total_units = 0

        for (w_code, d_code, sku), var in x.items():
            qty = int(round(var.solution_value()))
            if qty > 0:
                r_entry = route_info[(w_code, d_code)]
                unit_cost = r_entry["cost"]
                lead_time = r_entry["lead_time"]
                shipment_cost = round(qty * unit_cost, 2)
                total_transport_cost += shipment_cost
                total_units += qty

                d_name = dest_meta.get(d_code, {}).get("name", d_code)
                p_name = prod_meta.get(sku, {}).get("name", sku)

                shipments.append({
                    "source_warehouse_code": w_code,
                    "destination_code": d_code,
                    "destination_name": d_name,
                    "product_sku": sku,
                    "product_name": p_name,
                    "recommended_units": qty,
                    "unit_transport_cost": unit_cost,
                    "total_transport_cost": shipment_cost,
                    "lead_time_days": lead_time,
                    "estimated_expiry_risk_pct": None,  # Not modeled without store-level consumption data
                })

        shipments.sort(
            key=lambda s: (s["destination_code"], s["product_sku"], s["source_warehouse_code"])
        )

        # ------------------------------------------------------------------
        # 11. Extract Unmet Demand Accounting
        # ------------------------------------------------------------------
        unmet_demands: List[Dict[str, Any]] = []
        total_unmet_units = 0

        for (d_code, sku), u_var in u.items():
            unmet_qty = int(round(u_var.solution_value()))
            dem = demand_map.get((d_code, sku), 0)
            if unmet_qty > 0:
                total_unmet_units += unmet_qty
                unmet_demands.append({
                    "destination_code": d_code,
                    "destination_name": dest_meta.get(d_code, {}).get("name", d_code),
                    "product_sku": sku,
                    "product_name": prod_meta.get(sku, {}).get("name", sku),
                    "demanded_units": dem,
                    "fulfilled_units": dem - unmet_qty,
                    "unmet_units": unmet_qty,
                    "risk_category": risk_map.get((d_code, sku), "Moderate"),
                })

        unmet_demands.sort(key=lambda u_item: (-u_item["unmet_units"], u_item["destination_code"]))

        fulfillment_rate = (
            round(total_units / total_demanded_units, 4) if total_demanded_units > 0 else 1.0
        )
        target_met = (
            fulfillment_rate >= eff_min_fulfillment
            if eff_min_fulfillment is not None
            else True
        )
        elapsed_seconds = round(time.perf_counter() - start_time, 4)

        # ------------------------------------------------------------------
        # 12. Compute Greedy Baseline Comparison
        # ------------------------------------------------------------------
        baseline_result = solve_greedy_baseline(
            warehouses=warehouses,
            destinations=destinations,
            products=products,
            available_supply=available_supply,
            demand_targets=demand_targets,
            routes=routes,
            max_lead_time_days=lead_time_cutoff,
            inventory_items=inventory_items,
            as_of_date=as_of_date,
            min_arrival_shelf_life_days=eff_min_shelf_life,
            min_fulfillment_rate=eff_min_fulfillment,
        )

        comparison = {
            "baseline_total_units": baseline_result["total_units"],
            "baseline_total_cost": baseline_result["total_transport_cost"],
            "baseline_unmet_units": baseline_result["total_unmet_units"],
            "baseline_fulfillment_rate": baseline_result["fulfillment_rate"],
            "optimized_total_units": total_units,
            "optimized_total_cost": round(total_transport_cost, 2),
            "optimized_unmet_units": total_unmet_units,
            "optimized_fulfillment_rate": fulfillment_rate,
            "units_difference": total_units - baseline_result["total_units"],
            "cost_difference": round(total_transport_cost - baseline_result["total_transport_cost"], 2),
            "fulfillment_rate_difference": round(fulfillment_rate - baseline_result["fulfillment_rate"], 4),
        }

        return {
            "solver_status": status_str,
            "optimization_profile": opt_profile,
            "total_transport_cost": round(total_transport_cost, 2),
            "total_units": total_units,
            "total_demanded_units": total_demanded_units,
            "total_unmet_units": total_unmet_units,
            "fulfillment_rate": fulfillment_rate,
            "min_fulfillment_target_met": target_met,
            "expiry_waste_modeled": False,
            "solver_runtime_seconds": elapsed_seconds,
            "shipments": shipments,
            "unmet_demands": unmet_demands,
            "baseline_comparison": comparison,
            "warnings": warnings,
        }

    def _build_empty_result(
        self,
        solver_status: str,
        status_message: str,
        demand_map: Dict[Tuple[str, str], int],
        prod_meta: Dict[str, Dict[str, Any]],
        dest_meta: Dict[str, Dict[str, Any]],
        start_time: float,
        warnings: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Constructs an explicit honest failure response with full unmet demand."""
        unmet_list = []
        total_demand = sum(demand_map.values())
        for (d_code, sku), dem in demand_map.items():
            if dem > 0:
                unmet_list.append({
                    "destination_code": d_code,
                    "destination_name": dest_meta.get(d_code, {}).get("name", d_code),
                    "product_sku": sku,
                    "product_name": prod_meta.get(sku, {}).get("name", sku),
                    "demanded_units": dem,
                    "fulfilled_units": 0,
                    "unmet_units": dem,
                    "risk_category": "Critical",
                })

        return {
            "solver_status": solver_status,
            "status_message": status_message,
            "optimization_profile": self.profile,
            "total_transport_cost": 0.0,
            "total_units": 0,
            "total_demanded_units": total_demand,
            "total_unmet_units": total_demand,
            "fulfillment_rate": 0.0,
            "min_fulfillment_target_met": False,
            "expiry_waste_modeled": False,
            "solver_runtime_seconds": round(time.perf_counter() - start_time, 4),
            "shipments": [],
            "unmet_demands": unmet_list,
            "baseline_comparison": None,
            "warnings": warnings or [status_message],
        }
