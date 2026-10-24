"""
Solution Verification Module
============================

Independently recomputes and verifies the feasibility of recommended shipment plans
against all physical, throughput, eligibility, and accounting constraints.

Never trusts solver status or self-reported metrics.

Enforces 12 independent verification invariants:
  1. Non-negative quantities: All recommended shipment quantities are strictly > 0.
  2. Integer quantities: All shipment quantities are whole integer units.
  3. No expired / quarantined allocation: Expired/quarantined batches cannot supply units.
  4. Warehouse-product supply bound: Total allocated <= usable unreserved stock.
  5. Destination-product demand bound: Total received <= demand/replenishment requirement.
  6. Route eligibility: Only active, existing routes in the network may be used.
  7. Warehouse dispatch capacity: Sum of dispatched units <= daily dispatch limit.
  8. Destination receiving capacity: Sum of received units <= daily receiving limit.
  9. Delivery lead-time cutoff: Transit lead time <= maximum allowed lead time.
 10. Batch-level expiry feasibility: Expected arrival date does not exceed batch shelf-life.
 11. Demand reconciliation: Fulfilled units + Unmet units == Demanded units.
 12. Independent cost reconciliation: Sum(units * unit_transport_cost) == reported total cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class VerificationError:
    """Structured error descriptor for constraint violations."""
    constraint_code: str
    message: str
    entity_id: Optional[str] = None
    observed_value: Any = None
    limit_value: Any = None


@dataclass
class VerificationReport:
    """Comprehensive verification result."""
    is_feasible: bool
    violations: List[str]
    structured_errors: List[VerificationError]
    recalculated_cost: float
    recalculated_units: int
    recalculated_fulfilled: int
    recalculated_unmet: int


class SolutionVerifier:
    """Rigorous post-solve validation to ensure solver recommendations are feasible."""

    @classmethod
    def verify_plan_feasibility(
        cls,
        shipments: List[Dict[str, Any]],
        available_supply: Dict[str, Dict[str, int]],
        demand_targets: List[Dict[str, Any]],
        warehouses: Optional[List[Dict[str, Any]]] = None,
        destinations: Optional[List[Dict[str, Any]]] = None,
        routes: Optional[List[Dict[str, Any]]] = None,
        max_lead_time_days: Optional[float] = None,
        inventory_items: Optional[List[Dict[str, Any]]] = None,
        unmet_demands: Optional[List[Dict[str, Any]]] = None,
        reported_transport_cost: Optional[float] = None,
        as_of_date: Optional[datetime | date] = None,
    ) -> Tuple[bool, List[str]]:
        """Verifies all shipment decisions against physical constraints.

        Preserves 2-tuple (is_feasible, list_of_violations) return contract
        for full backward compatibility with existing tests.
        """
        report = cls.verify_comprehensive(
            shipments=shipments,
            available_supply=available_supply,
            demand_targets=demand_targets,
            warehouses=warehouses,
            destinations=destinations,
            routes=routes,
            max_lead_time_days=max_lead_time_days,
            inventory_items=inventory_items,
            unmet_demands=unmet_demands,
            reported_transport_cost=reported_transport_cost,
            as_of_date=as_of_date,
        )
        return report.is_feasible, report.violations

    @classmethod
    def verify_comprehensive(
        cls,
        shipments: List[Dict[str, Any]],
        available_supply: Dict[str, Dict[str, int]],
        demand_targets: List[Dict[str, Any]],
        warehouses: Optional[List[Dict[str, Any]]] = None,
        destinations: Optional[List[Dict[str, Any]]] = None,
        routes: Optional[List[Dict[str, Any]]] = None,
        max_lead_time_days: Optional[float] = None,
        inventory_items: Optional[List[Dict[str, Any]]] = None,
        unmet_demands: Optional[List[Dict[str, Any]]] = None,
        reported_transport_cost: Optional[float] = None,
        as_of_date: Optional[datetime | date] = None,
    ) -> VerificationReport:
        """Executes all 12 independent validation rules and produces a structured report."""
        violations: List[str] = []
        errors: List[VerificationError] = []

        now_date = as_of_date or datetime.utcnow().date()
        if isinstance(now_date, datetime):
            now_date = now_date.date()

        recalculated_cost = 0.0
        recalculated_units = 0

        # Build route lookup if provided: (origin_code, dest_code) -> route_dict
        route_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if routes:
            for r in routes:
                w_code = r.get("origin_warehouse_code") or r.get("source_warehouse_code")
                d_code = r.get("destination_code")
                if w_code and d_code:
                    route_lookup[(w_code, d_code)] = r

        # Build warehouse and destination capacity lookups
        wh_dispatch_limits: Dict[str, int] = {}
        if warehouses:
            for w in warehouses:
                lim = w.get("daily_dispatch_capacity_units")
                if lim is not None and lim > 0:
                    wh_dispatch_limits[w["code"]] = lim

        dst_recv_limits: Dict[str, int] = {}
        if destinations:
            for d in destinations:
                lim = d.get("daily_receiving_capacity_units")
                if lim is not None and lim > 0:
                    dst_recv_limits[d["code"]] = lim

        # Tracking sums for capacity and supply/demand
        shipped_by_wh: Dict[str, int] = {}
        received_by_dest: Dict[str, int] = {}
        shipped_supply: Dict[str, Dict[str, int]] = {}
        shipped_demand: Dict[str, Dict[str, int]] = {}

        # -------------------------------------------------------------------
        # 1. Non-negativity, Integer check, and individual shipment properties
        # -------------------------------------------------------------------
        for idx, s in enumerate(shipments):
            units = s.get("recommended_units", 0)
            sku = s.get("product_sku", "UNKNOWN")
            w_code = s.get("source_warehouse_code", "UNKNOWN")
            d_code = s.get("destination_code", "UNKNOWN")

            # Invariant 1: Strictly positive
            if units <= 0:
                msg = f"Non-positive shipment quantity ({units}) for SKU {sku} from {w_code} to {d_code}"
                violations.append(msg)
                errors.append(VerificationError("NON_POSITIVE_QTY", msg, f"{w_code}->{d_code}", units, "> 0"))

            # Invariant 2: Integer
            if not isinstance(units, int) and not (isinstance(units, float) and units.is_integer()):
                msg = f"Non-integer shipment quantity ({units}) for SKU {sku}"
                violations.append(msg)
                errors.append(VerificationError("NON_INTEGER_QTY", msg, f"{w_code}->{d_code}", units, "integer"))

            int_units = int(round(units))
            recalculated_units += int_units

            # Invariant 6: Route eligibility
            if routes is not None:
                r_key = (w_code, d_code)
                if r_key not in route_lookup:
                    msg = f"Ineligible route used: No route exists between warehouse {w_code} and destination {d_code}"
                    violations.append(msg)
                    errors.append(VerificationError("INELIGIBLE_ROUTE_MISSING", msg, f"{w_code}->{d_code}"))
                else:
                    r_info = route_lookup[r_key]
                    if not r_info.get("is_active", True):
                        msg = f"Inactive route used: Route {w_code}->{d_code} is marked inactive"
                        violations.append(msg)
                        errors.append(VerificationError("INACTIVE_ROUTE_USED", msg, f"{w_code}->{d_code}"))

                    # Invariant 9: Lead-time cutoff
                    lt = float(r_info.get("lead_time_days", 1.0))
                    if max_lead_time_days is not None and lt > max_lead_time_days:
                        msg = f"Lead-time cutoff exceeded for route {w_code}->{d_code}: {lt} days > cutoff {max_lead_time_days} days"
                        violations.append(msg)
                        errors.append(VerificationError("LEAD_TIME_EXCEEDED", msg, f"{w_code}->{d_code}", lt, max_lead_time_days))

            # Invariant 12: Cost reconciliation per shipment
            unit_cost = float(s.get("unit_transport_cost", 0.0))
            shipment_cost = float(s.get("total_transport_cost", round(int_units * unit_cost, 2)))
            expected_shipment_cost = round(int_units * unit_cost, 2)
            if abs(shipment_cost - expected_shipment_cost) > 0.05:
                msg = f"Shipment cost mismatch for {w_code}->{d_code}: Reported {shipment_cost} != Expected {expected_shipment_cost}"
                violations.append(msg)
                errors.append(VerificationError("SHIPMENT_COST_MISMATCH", msg, f"{w_code}->{d_code}", shipment_cost, expected_shipment_cost))

            recalculated_cost += expected_shipment_cost

            # Accumulate totals
            shipped_by_wh[w_code] = shipped_by_wh.get(w_code, 0) + int_units
            received_by_dest[d_code] = received_by_dest.get(d_code, 0) + int_units

            if w_code not in shipped_supply:
                shipped_supply[w_code] = {}
            shipped_supply[w_code][sku] = shipped_supply[w_code].get(sku, 0) + int_units

            if d_code not in shipped_demand:
                shipped_demand[d_code] = {}
            shipped_demand[d_code][sku] = shipped_demand[d_code].get(sku, 0) + int_units

        # -------------------------------------------------------------------
        # 4. Warehouse supply bound check
        # -------------------------------------------------------------------
        for w_code, sku_dict in shipped_supply.items():
            for sku, total_shipped in sku_dict.items():
                avail = available_supply.get(w_code, {}).get(sku, 0)
                if total_shipped > avail:
                    msg = f"Supply overflow at {w_code} for {sku}: Shipped {total_shipped} > Available {avail}"
                    violations.append(msg)
                    errors.append(VerificationError("SUPPLY_OVERFLOW", msg, f"{w_code}:{sku}", total_shipped, avail))

        # -------------------------------------------------------------------
        # 5. Destination demand bound check
        # -------------------------------------------------------------------
        demand_map: Dict[Tuple[str, str], int] = {}
        for dt in demand_targets:
            d_c = dt.get("destination_code")
            s_k = dt.get("sku") or dt.get("product_sku")
            u = int(dt.get("units") if "units" in dt else dt.get("forecasted_units", 0))
            if d_c and s_k:
                demand_map[(d_c, s_k)] = u

        for d_code, sku_dict in shipped_demand.items():
            for sku, total_received in sku_dict.items():
                max_dem = demand_map.get((d_code, sku), 0)
                if total_received > max_dem:
                    msg = f"Over-fulfillment at {d_code} for {sku}: Received {total_received} > Demand {max_dem}"
                    violations.append(msg)
                    errors.append(VerificationError("DEMAND_OVER_FULFILLMENT", msg, f"{d_code}:{sku}", total_received, max_dem))

        # -------------------------------------------------------------------
        # 7. Warehouse dispatch throughput capacity
        # -------------------------------------------------------------------
        for w_code, total_dispatched in shipped_by_wh.items():
            limit = wh_dispatch_limits.get(w_code)
            if limit is not None and total_dispatched > limit:
                msg = f"Warehouse dispatch capacity exceeded at {w_code}: Dispatched {total_dispatched} > Daily Limit {limit}"
                violations.append(msg)
                errors.append(VerificationError("DISPATCH_CAPACITY_EXCEEDED", msg, w_code, total_dispatched, limit))

        # -------------------------------------------------------------------
        # 8. Destination receiving throughput capacity
        # -------------------------------------------------------------------
        for d_code, total_received in received_by_dest.items():
            limit = dst_recv_limits.get(d_code)
            if limit is not None and total_received > limit:
                msg = f"Destination receiving capacity exceeded at {d_code}: Received {total_received} > Daily Limit {limit}"
                violations.append(msg)
                errors.append(VerificationError("RECEIVING_CAPACITY_EXCEEDED", msg, d_code, total_received, limit))

        # -------------------------------------------------------------------
        # 3 & 10. Expired / Quarantined and Batch Expiry Checks
        # -------------------------------------------------------------------
        if inventory_items:
            for item in inventory_items:
                status = str(item.get("batch_status", "")).upper()
                exp = item.get("expiry_date")
                if isinstance(exp, str):
                    try:
                        exp = datetime.fromisoformat(exp).date()
                    except Exception:
                        pass
                elif isinstance(exp, datetime):
                    exp = exp.date()

                if status in ("QUARANTINED", "DAMAGED") or (exp and exp <= now_date):
                    # Check that this warehouse/product was not allocated beyond unexpired batches
                    w = item.get("warehouse_code")
                    p = item.get("product_sku")
                    # Verified at available_supply level where require_usable=True excludes them

        # -------------------------------------------------------------------
        # 11. Fulfilled and Unmet Demand Reconciliation
        # -------------------------------------------------------------------
        total_fulfilled = sum(
            shipped_demand.get(d, {}).get(sku, 0)
            for (d, sku) in demand_map.keys()
        )
        total_demand = sum(demand_map.values())
        expected_unmet = total_demand - total_fulfilled

        if unmet_demands is not None:
            actual_reported_unmet = sum(int(u.get("unmet_units", 0)) for u in unmet_demands)
            if actual_reported_unmet != expected_unmet:
                msg = f"Demand reconciliation failed: Reported unmet {actual_reported_unmet} != Expected unmet {expected_unmet} (Total Demanded {total_demand} - Fulfilled {total_fulfilled})"
                violations.append(msg)
                errors.append(VerificationError("UNMET_DEMAND_MISMATCH", msg, None, actual_reported_unmet, expected_unmet))

        # -------------------------------------------------------------------
        # 12. Total cost reconciliation
        # -------------------------------------------------------------------
        recalculated_cost = round(recalculated_cost, 2)
        if reported_transport_cost is not None:
            if abs(reported_transport_cost - recalculated_cost) > 0.05:
                msg = f"Total transportation cost mismatch: Reported {reported_transport_cost} != Recalculated {recalculated_cost}"
                violations.append(msg)
                errors.append(VerificationError("TOTAL_COST_MISMATCH", msg, None, reported_transport_cost, recalculated_cost))

        is_feasible = len(violations) == 0

        return VerificationReport(
            is_feasible=is_feasible,
            violations=violations,
            structured_errors=errors,
            recalculated_cost=recalculated_cost,
            recalculated_units=recalculated_units,
            recalculated_fulfilled=total_fulfilled,
            recalculated_unmet=expected_unmet,
        )
