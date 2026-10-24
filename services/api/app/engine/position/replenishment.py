"""
Replenishment Requirements Engine
==================================

Calculates per-product-per-destination replenishment requirements by
combining inventory position, lead-time demand forecast, and safety stock.

Formulas (all documented)
--------------------------
  lead_time_demand = daily_mean_demand × lead_time_days          [float]
  safety_stock     = z × σ_d × √L                               [float → ceil to int]
  threshold        = lead_time_demand + safety_stock             [float]
  gross_req        = max(0, threshold - projected_position)      [float]
  replen_qty       = max(0, ceil(gross_req))                     [int]

Projected inventory position
-----------------------------
  projected_position = usable_warehouse_stock_at_destination
                     + incoming_committed_qty
                     (- no forecast demand deduction here: threshold already
                        accounts for consumption during lead time)

  NOTE: The current database does NOT have a DestinationInventory table.
  This is a documented gap (see Database Gap section below).  Until that
  table is added, destination usable stock is assumed to be 0 and a
  warning is emitted.  Warehouse stock is NOT used as destination stock.

  Incoming shipments: The ShipmentRecommendation table records
  RECOMMENDED shipments from past planning runs.  These are planning
  outputs, not confirmed dispatches.  Until a ConfirmedDispatch table is
  added, incoming_committed_qty = 0 and a warning is emitted.

Double-counting prevention
--------------------------
  1. Warehouse stock and destination stock are separate quantities.
     They must NOT be summed.
  2. Reserved warehouse units are excluded from available supply by
     InventoryPositionAnalyzer before this engine runs.
  3. Safety stock is a BUFFER, not physical stock.  It must NOT be added
     to on-hand quantity.
  4. Lead-time demand must NOT be deducted from on-hand stock before
     computing projected_position — it is already encoded in the threshold.

Route-selection policy (when multiple active routes exist)
----------------------------------------------------------
  When more than one active route connects a warehouse to a destination,
  this engine does NOT select arbitrarily.  The policy is:
    1. Use the route with the MINIMUM lead_time_days (fastest delivery).
    2. Ties broken by MINIMUM unit_transport_cost.
  This is documented and reported in the result.  The optimizer may later
  choose a different route based on cost/capacity trade-offs.

Fractional lead-time policy
----------------------------
  Lead times in the Route table are float (days).  Fractional lead times
  (e.g., 1.5 days) are used directly in the safety-stock formula:
    SS = z × σ_d × √L
  For lead_time_demand, fractional days are multiplied directly:
    lead_time_demand = mean_daily_demand × L
  This means a 1.5-day lead time uses 1.5 × daily mean, not rounded to 2.

Database gaps identified (not invented — documented)
----------------------------------------------------
  GAP-1: No DestinationInventory table.
    Impact: projected_position cannot include destination on-hand stock.
    Minimum extension needed: a DestinationStockSnapshot model with
    (destination_id, product_id, snapshot_date, on_hand_units).
    Until added: destination_usable_units = 0, warning emitted.

  GAP-2: No ConfirmedDispatch / InTransit table.
    Impact: incoming_committed_qty is always 0.
    Until added: incoming_qty = 0, warning emitted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.engine.position.safety_stock import (
    SafetyStockConfig,
    SafetyStockResult,
    compute_safety_stock,
)
from app.engine.forecast.data_prep import prepare_demand_series


# ---------------------------------------------------------------------------
# Warning codes
# ---------------------------------------------------------------------------

WARN_NO_ACTIVE_ROUTE = "no_active_route_found"
WARN_MULTIPLE_ROUTES_MIN_LEAD = "multiple_routes_selected_min_lead_time"
WARN_NO_DESTINATION_INVENTORY = "destination_inventory_not_tracked_assumed_zero"
WARN_NO_INCOMING_SHIPMENTS = "incoming_shipments_not_tracked_assumed_zero"
WARN_REPLEN_ZERO_DEMAND = "replenishment_zero_demand_no_history"
WARN_INSUFFICIENT_HISTORY = "replenishment_insufficient_demand_history"


# ---------------------------------------------------------------------------
# Risk category rules (documented, not calibrated probabilities)
# ---------------------------------------------------------------------------

RISK_CRITICAL = "Critical"
RISK_HIGH = "High"
RISK_MODERATE = "Moderate"
RISK_LOW = "Low"
RISK_INSUFFICIENT_DATA = "InsufficientData"

RISK_RULES_DOC = """
Risk category assignment rules (cover days vs lead time):
  Critical         : cover_days == 0 (out of stock)
  High             : 0 < cover_days <= lead_time_days  (will stock out before replenishment arrives)
  Moderate         : lead_time_days < cover_days <= lead_time_days + safety_stock_days
  Low              : cover_days > lead_time_days + safety_stock_days
  InsufficientData : daily_demand == 0 or history unavailable

These categories are NOT calibrated stockout probabilities.
They are heuristic risk bands based on cover vs lead-time comparison.
"""


def assign_risk_category(
    cover_days: float,
    lead_time_days: float,
    safety_stock_days: float,
    daily_demand: float,
) -> str:
    """Assigns a risk category based on documented cover-day rules.

    Parameters
    ----------
    cover_days:
        Estimated days of inventory cover at the destination.
    lead_time_days:
        Route lead time (days).
    safety_stock_days:
        Safety stock expressed as days of demand (SS_units / daily_demand).
    daily_demand:
        Mean daily demand (units/day).

    Returns
    -------
    One of: Critical, High, Moderate, Low, InsufficientData.
    """
    if daily_demand <= 0.0:
        return RISK_INSUFFICIENT_DATA
    if cover_days <= 0.0:
        return RISK_CRITICAL
    if cover_days <= lead_time_days:
        return RISK_HIGH
    if cover_days <= lead_time_days + safety_stock_days:
        return RISK_MODERATE
    return RISK_LOW


# ---------------------------------------------------------------------------
# Route selection
# ---------------------------------------------------------------------------

@dataclass
class SelectedRoute:
    warehouse_code: str
    warehouse_id: int
    destination_code: str
    destination_id: int
    lead_time_days: float
    unit_transport_cost: float
    route_id: int
    selection_reason: str


def select_best_route(
    routes: List[Dict[str, Any]],
    warehouse_code: str,
    destination_code: str,
) -> Optional[SelectedRoute]:
    """Selects the best active route per the documented policy.

    Policy: minimum lead_time_days; ties broken by minimum unit_transport_cost.

    Parameters
    ----------
    routes:
        List of route dicts with keys:
        id, origin_warehouse_id, destination_id, origin_warehouse_code,
        destination_code, lead_time_days, unit_transport_cost, is_active.
    warehouse_code:
        Filter for origin warehouse.
    destination_code:
        Filter for destination.

    Returns
    -------
    SelectedRoute or None if no active route found.
    """
    active = [
        r for r in routes
        if r.get("origin_warehouse_code") == warehouse_code
        and r.get("destination_code") == destination_code
        and r.get("is_active", True)
    ]

    if not active:
        return None

    best = min(active, key=lambda r: (r["lead_time_days"], r["unit_transport_cost"]))
    reason = "minimum_lead_time"
    if len(active) > 1:
        reason = "minimum_lead_time_from_multiple_active_routes"

    return SelectedRoute(
        warehouse_code=warehouse_code,
        warehouse_id=best.get("origin_warehouse_id", 0),
        destination_code=destination_code,
        destination_id=best.get("destination_id", 0),
        lead_time_days=best["lead_time_days"],
        unit_transport_cost=best["unit_transport_cost"],
        route_id=best.get("id", 0),
        selection_reason=reason,
    )


# ---------------------------------------------------------------------------
# Replenishment result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ReplenishmentRequirement:
    """Full replenishment analysis for a single product-destination pair.

    All quantities are in the same unit as demand (e.g., cases, units).
    """
    product_id: int
    product_sku: str
    product_name: str
    destination_id: int
    destination_code: str
    destination_name: str

    # Lead time
    lead_time_days: float
    warehouse_code: Optional[str]
    route_selection_reason: str

    # Demand
    daily_mean_demand: float
    lead_time_demand: float              # daily_mean × lead_time_days (float)
    forecast_method: str
    forecast_warnings: List[str]

    # Safety stock
    safety_stock: SafetyStockResult

    # Replenishment threshold
    replenishment_threshold: float       # lead_time_demand + safety_stock_units

    # Inventory position
    destination_usable_units: int        # always 0 until GAP-1 is filled
    incoming_committed_units: int        # always 0 until GAP-2 is filled
    projected_position: float            # destination_usable + incoming

    # Replenishment requirement
    gross_replenishment: float           # max(0, threshold - projected_position)
    replenishment_qty: int               # ceil(gross_replenishment), non-negative integer

    # Risk assessment
    cover_days: Optional[float]          # None if daily_demand == 0
    safety_stock_days: Optional[float]   # SS_units / daily_demand
    risk_category: str

    # Reason codes and explanations
    reason_codes: List[str]
    explanation: str

    # Data quality
    warnings: List[str]
    history_observations_used: int


# ---------------------------------------------------------------------------
# Main calculation function
# ---------------------------------------------------------------------------

def calculate_replenishment(
    product_id: int,
    product_sku: str,
    product_name: str,
    destination_id: int,
    destination_code: str,
    destination_name: str,
    demand_history_rows: List[Dict[str, Any]],
    available_routes: List[Dict[str, Any]],
    warehouse_code: str,
    ss_config: Optional[SafetyStockConfig] = None,
    as_of_date: Optional[date] = None,
    forecast_method: str = "ewma",
    ewma_alpha: float = 0.3,
    is_simulated_data: bool = False,
) -> ReplenishmentRequirement:
    """Calculates the full replenishment requirement for one product-destination pair.

    Parameters
    ----------
    demand_history_rows:
        Raw demand records for this (product, destination) pair.
    available_routes:
        All routes (already filtered to relevant warehouse-destination pairs
        or the full route list — function filters internally).
    warehouse_code:
        The warehouse being evaluated as the supply source.
    ss_config:
        Safety-stock configuration.
    as_of_date:
        Planning date.  Defaults to today (UTC).
    forecast_method, ewma_alpha:
        Forwarded to the forecasting engine.

    Returns
    -------
    ReplenishmentRequirement
    """
    if as_of_date is None:
        as_of_date = datetime.utcnow().date()

    if ss_config is None:
        ss_config = SafetyStockConfig()
    ss_config.validate()

    warnings: List[str] = []
    reason_codes: List[str] = []

    # ------------------------------------------------------------------
    # 1. Route selection
    # ------------------------------------------------------------------
    route = select_best_route(available_routes, warehouse_code, destination_code)

    if route is None:
        warnings.append(WARN_NO_ACTIVE_ROUTE)
        reason_codes.append("NO_ROUTE")
        # Cannot compute meaningful replenishment without a route lead time
        return ReplenishmentRequirement(
            product_id=product_id,
            product_sku=product_sku,
            product_name=product_name,
            destination_id=destination_id,
            destination_code=destination_code,
            destination_name=destination_name,
            lead_time_days=0.0,
            warehouse_code=warehouse_code,
            route_selection_reason="none_found",
            daily_mean_demand=0.0,
            lead_time_demand=0.0,
            forecast_method=forecast_method,
            forecast_warnings=[],
            safety_stock=compute_safety_stock([], 0.0, ss_config, is_simulated_data),
            replenishment_threshold=0.0,
            destination_usable_units=0,
            incoming_committed_units=0,
            projected_position=0.0,
            gross_replenishment=0.0,
            replenishment_qty=0,
            cover_days=None,
            safety_stock_days=None,
            risk_category=RISK_INSUFFICIENT_DATA,
            reason_codes=reason_codes,
            explanation="No active route found between warehouse and destination.",
            warnings=warnings,
            history_observations_used=0,
        )

    if "multiple" in route.selection_reason:
        warnings.append(WARN_MULTIPLE_ROUTES_MIN_LEAD)

    lead_time_days = route.lead_time_days

    # ------------------------------------------------------------------
    # 2. Prepare demand series (reuse forecasting data_prep)
    # ------------------------------------------------------------------
    series = prepare_demand_series(demand_history_rows, as_of_date=as_of_date)
    history_used = series.observation_count
    daily_demands = [float(d) for d in series.demands]

    # ------------------------------------------------------------------
    # 3. Forecast lead-time demand (using actual lead time, not fixed horizon)
    # ------------------------------------------------------------------
    # The forecasting engine supports horizons {7, 14, 30}.
    # Lead time is typically < 7 days; we compute fractionally from daily_mean.
    # We use the EWMA/naive daily_mean_demand and multiply by lead_time_days.

    from app.engine.forecast.methods import (
        forecast as do_forecast,
        METHOD_EWMA,
        METHOD_NAIVE,
        SUPPORTED_HORIZONS,
    )

    # Use 7d horizon to get daily_mean, then scale to actual lead time
    snap_horizon = 7
    fc_result = do_forecast(
        series,
        method=forecast_method,
        horizon_days=snap_horizon,
        ewma_alpha=ewma_alpha,
    )

    if not fc_result.method_available:
        fallback = do_forecast(series, METHOD_NAIVE, snap_horizon)
        if fallback.method_available:
            fc_result = fallback
        else:
            warnings.append(WARN_INSUFFICIENT_HISTORY)
            reason_codes.append("INSUFFICIENT_DEMAND_HISTORY")

    daily_mean = fc_result.daily_mean_demand if fc_result.method_available else 0.0
    fc_warnings = fc_result.warnings
    actual_forecast_method = fc_result.method if fc_result.method_available else "unavailable"

    # Scale to actual lead time (fractional days supported)
    lead_time_demand = round(daily_mean * lead_time_days, 4)

    # ------------------------------------------------------------------
    # 4. Safety stock
    # ------------------------------------------------------------------
    ss_result = compute_safety_stock(
        daily_demands=daily_demands,
        lead_time_days=lead_time_days,
        config=ss_config,
        is_simulated_data=is_simulated_data,
    )
    warnings.extend(ss_result.warnings)

    # ------------------------------------------------------------------
    # 5. Replenishment threshold
    # ------------------------------------------------------------------
    # threshold = lead_time_demand + safety_stock_units (float)
    replenishment_threshold = lead_time_demand + ss_result.safety_stock_units

    # ------------------------------------------------------------------
    # 6. Projected inventory position
    #    GAP-1: destination on-hand = 0 (not tracked)
    #    GAP-2: incoming committed = 0 (not tracked)
    # ------------------------------------------------------------------
    destination_usable_units = 0
    incoming_committed_units = 0
    warnings.append(WARN_NO_DESTINATION_INVENTORY)
    warnings.append(WARN_NO_INCOMING_SHIPMENTS)
    reason_codes.append("DESTINATION_STOCK_NOT_TRACKED")

    projected_position = float(destination_usable_units + incoming_committed_units)

    # ------------------------------------------------------------------
    # 7. Gross replenishment and integer quantity
    # ------------------------------------------------------------------
    gross_replenishment = max(0.0, replenishment_threshold - projected_position)
    replenishment_qty = math.ceil(gross_replenishment)

    # ------------------------------------------------------------------
    # 8. Inventory cover and risk category
    # ------------------------------------------------------------------
    if daily_mean > 0:
        cover_days = round(projected_position / daily_mean, 2)
        ss_days = round(ss_result.safety_stock_units / daily_mean, 2)
    else:
        cover_days = None
        ss_days = None

    risk_cat = assign_risk_category(
        cover_days=cover_days if cover_days is not None else 0.0,
        lead_time_days=lead_time_days,
        safety_stock_days=ss_days if ss_days is not None else 0.0,
        daily_demand=daily_mean,
    )

    # ------------------------------------------------------------------
    # 9. Reason codes and human explanation
    # ------------------------------------------------------------------
    if replenishment_qty > 0:
        reason_codes.append("REPLENISHMENT_REQUIRED")
    else:
        reason_codes.append("REPLENISHMENT_NOT_REQUIRED")

    explanation = (
        f"Lead time: {lead_time_days}d. "
        f"Lead-time demand: {lead_time_demand:.1f} units "
        f"({daily_mean:.1f} units/day × {lead_time_days}d). "
        f"Safety stock: {ss_result.safety_stock_int} units "
        f"(method={ss_result.method_used}). "
        f"Threshold: {replenishment_threshold:.1f} units. "
        f"Projected position: {projected_position:.0f} units "
        f"(destination stock not tracked; incoming not tracked). "
        f"Gross requirement: {gross_replenishment:.1f} → "
        f"replenish {replenishment_qty} units. "
        f"Risk: {risk_cat}."
    )

    return ReplenishmentRequirement(
        product_id=product_id,
        product_sku=product_sku,
        product_name=product_name,
        destination_id=destination_id,
        destination_code=destination_code,
        destination_name=destination_name,
        lead_time_days=lead_time_days,
        warehouse_code=warehouse_code,
        route_selection_reason=route.selection_reason,
        daily_mean_demand=daily_mean,
        lead_time_demand=lead_time_demand,
        forecast_method=actual_forecast_method,
        forecast_warnings=fc_warnings,
        safety_stock=ss_result,
        replenishment_threshold=round(replenishment_threshold, 4),
        destination_usable_units=destination_usable_units,
        incoming_committed_units=incoming_committed_units,
        projected_position=projected_position,
        gross_replenishment=round(gross_replenishment, 4),
        replenishment_qty=replenishment_qty,
        cover_days=cover_days,
        safety_stock_days=ss_days,
        risk_category=risk_cat,
        reason_codes=reason_codes,
        explanation=explanation,
        warnings=list(set(warnings)),   # deduplicate
        history_observations_used=history_used,
    )


# ---------------------------------------------------------------------------
# Optimizer integration contract
# ---------------------------------------------------------------------------

def to_optimizer_contract(req: ReplenishmentRequirement) -> Dict[str, Any]:
    """Converts a ReplenishmentRequirement to the optimizer-facing contract dict.

    The optimizer must NOT treat replenishment_qty as guaranteed available supply.
    Warehouse usable stock, route eligibility, transport capacity, and destination
    receiving capacity remain independent constraints in the solver.

    Parameters
    ----------
    req:
        A computed ReplenishmentRequirement.

    Returns
    -------
    Dict with the optimizer integration contract fields.
    """
    return {
        # Identifiers
        "product_id": req.product_id,
        "product_sku": req.product_sku,
        "destination_id": req.destination_id,
        "destination_code": req.destination_code,

        # Replenishment signal (NOT guaranteed available — see note above)
        "replenishment_qty": req.replenishment_qty,
        "gross_replenishment": req.gross_replenishment,

        # Lead-time demand
        "lead_time_demand": req.lead_time_demand,
        "daily_mean_demand": req.daily_mean_demand,
        "lead_time_days": req.lead_time_days,

        # Safety stock
        "safety_stock_units": req.safety_stock.safety_stock_int,
        "safety_stock_method": req.safety_stock.method_used,

        # Inventory position at destination (0 until GAP-1 filled)
        "projected_position": req.projected_position,
        "destination_stock_tracked": False,   # explicit flag for optimizer

        # Risk
        "risk_category": req.risk_category,

        # Data quality
        "warnings": req.warnings,
        "history_used": req.history_observations_used,
        "forecast_method": req.forecast_method,

        # Optimizer contract notes (read-only documentation)
        "_contract_notes": [
            "replenishment_qty is the SIGNAL, not a supply guarantee.",
            "Warehouse usable stock is a separate constraint.",
            "Route eligibility must be checked independently.",
            "destination_stock_tracked=False means projected_position is 0 (GAP-1).",
        ],
    }
