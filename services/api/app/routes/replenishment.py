"""Replenishment Requirements and Inventory Position API route handlers."""

from collections import defaultdict
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import (
    DailyDemandHistory,
    Destination,
    InventoryItem,
    Product,
    Route,
    Warehouse,
)
from app.engine.position.inventory_position import InventoryPositionAnalyzer
from app.engine.position.replenishment import (
    ReplenishmentRequirement,
    assign_risk_category,
    calculate_replenishment,
    to_optimizer_contract,
    RISK_CRITICAL,
    RISK_HIGH,
    RISK_MODERATE,
    RISK_LOW,
    RISK_INSUFFICIENT_DATA,
)
from app.engine.position.safety_stock import SafetyStockConfig
from app.schemas.replenishment import (
    OptimizerContractItem,
    OptimizerContractResponse,
    ReplenishmentRequest,
    ReplenishmentRequirementSchema,
    ReplenishmentResponse,
    ReplenishmentSummaryRequest,
    ReplenishmentSummaryResponse,
    SafetyStockResultSchema,
)

router = APIRouter(prefix="/replenishment", tags=["Replenishment"])

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _req_to_schema(req: ReplenishmentRequirement) -> ReplenishmentRequirementSchema:
    """Converts an engine result to the Pydantic response schema."""
    return ReplenishmentRequirementSchema(
        product_id=req.product_id,
        product_sku=req.product_sku,
        product_name=req.product_name,
        destination_id=req.destination_id,
        destination_code=req.destination_code,
        destination_name=req.destination_name,
        lead_time_days=req.lead_time_days,
        warehouse_code=req.warehouse_code,
        route_selection_reason=req.route_selection_reason,
        daily_mean_demand=req.daily_mean_demand,
        lead_time_demand=req.lead_time_demand,
        forecast_method=req.forecast_method,
        forecast_warnings=req.forecast_warnings,
        safety_stock=SafetyStockResultSchema(
            safety_stock_units=req.safety_stock.safety_stock_units,
            safety_stock_int=req.safety_stock.safety_stock_int,
            method_used=req.safety_stock.method_used,
            mean_daily_demand=req.safety_stock.mean_daily_demand,
            stddev_daily_demand=req.safety_stock.stddev_daily_demand,
            lead_time_days=req.safety_stock.lead_time_days,
            observations_used=req.safety_stock.observations_used,
            warnings=req.safety_stock.warnings,
            is_simulated_data=req.safety_stock.is_simulated_data,
        ),
        replenishment_threshold=req.replenishment_threshold,
        destination_usable_units=req.destination_usable_units,
        incoming_committed_units=req.incoming_committed_units,
        projected_position=req.projected_position,
        gross_replenishment=req.gross_replenishment,
        replenishment_qty=req.replenishment_qty,
        cover_days=req.cover_days,
        safety_stock_days=req.safety_stock_days,
        risk_category=req.risk_category,
        reason_codes=req.reason_codes,
        explanation=req.explanation,
        warnings=req.warnings,
        history_observations_used=req.history_observations_used,
    )


def _risk_rank(category: str) -> int:
    """Returns numeric rank for risk-filter comparison (higher = more urgent)."""
    return {
        RISK_CRITICAL: 4,
        RISK_HIGH: 3,
        RISK_MODERATE: 2,
        RISK_LOW: 1,
        RISK_INSUFFICIENT_DATA: 0,
    }.get(category, 0)


OPTIMIZER_CAVEATS = [
    "replenishment_qty is a demand signal, not a supply guarantee.",
    "Warehouse usable stock is a separate constraint enforced by the solver.",
    "Route eligibility, transport capacity, and receiving limits are not checked here.",
    "destination_stock_tracked=False: destination on-hand is assumed 0 (GAP-1 pending).",
    "incoming_committed_units=0: in-transit stock not tracked (GAP-2 pending).",
    "All metrics are from deterministically simulated data. Validate before production use.",
]


# ---------------------------------------------------------------------------
# POST /api/v1/replenishment  — single product-destination
# ---------------------------------------------------------------------------

@router.post("", response_model=ReplenishmentResponse, status_code=200)
def calculate_single_replenishment(
    request: ReplenishmentRequest,
    db: Session = Depends(get_db),
):
    """Calculates replenishment requirement for a specific product-destination pair.

    Evaluates all active routes from available warehouses (or a specific warehouse
    if warehouse_id is provided).

    Returns replenishment quantity, safety stock, risk category, and explanations.
    """
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(404, f"Product {request.product_id} not found.")

    destination = db.query(Destination).filter(Destination.id == request.destination_id).first()
    if not destination:
        raise HTTPException(404, f"Destination {request.destination_id} not found.")

    # Fetch demand history
    rows = (
        db.query(DailyDemandHistory)
        .filter(
            DailyDemandHistory.product_id == request.product_id,
            DailyDemandHistory.destination_id == request.destination_id,
        )
        .order_by(DailyDemandHistory.demand_date.asc())
        .all()
    )
    demand_rows = [
        {
            "demand_date": r.demand_date,
            "quantity_demanded": r.quantity_demanded,
            "quantity_sold": r.quantity_sold,
            "is_simulated": r.is_simulated,
        }
        for r in rows
    ]

    # Fetch routes to this destination
    route_query = (
        db.query(Route, Warehouse.code.label("wh_code"))
        .join(Warehouse, Route.origin_warehouse_id == Warehouse.id)
        .filter(
            Route.destination_id == request.destination_id,
            Route.is_active == True,
        )
    )
    if request.warehouse_id is not None:
        route_query = route_query.filter(Route.origin_warehouse_id == request.warehouse_id)

    route_records = route_query.all()
    routes_dicts = [
        {
            "id": r.id,
            "origin_warehouse_id": r.origin_warehouse_id,
            "destination_id": r.destination_id,
            "origin_warehouse_code": wh_code,
            "destination_code": destination.code,
            "lead_time_days": r.lead_time_days,
            "unit_transport_cost": r.unit_transport_cost,
            "is_active": r.is_active,
        }
        for r, wh_code in route_records
    ]

    if not routes_dicts:
        raise HTTPException(
            400,
            f"No active routes found for destination {destination.code} "
            + (f"from warehouse {request.warehouse_id}." if request.warehouse_id else "from any warehouse."),
        )

    # Get unique warehouse codes from routes
    wh_codes: List[str] = list({r["origin_warehouse_code"] for r in routes_dicts})

    as_of = request.as_of_date
    ss_cfg = SafetyStockConfig(
        service_level_z=request.safety_stock_config.service_level_z,
        fallback_factor=request.safety_stock_config.fallback_factor,
        min_safety_stock_units=request.safety_stock_config.min_safety_stock_units,
    )

    requirements: List[ReplenishmentRequirementSchema] = []
    for wh_code in wh_codes:
        req = calculate_replenishment(
            product_id=product.id,
            product_sku=product.sku,
            product_name=product.name,
            destination_id=destination.id,
            destination_code=destination.code,
            destination_name=destination.name,
            demand_history_rows=demand_rows,
            available_routes=routes_dicts,
            warehouse_code=wh_code,
            ss_config=ss_cfg,
            as_of_date=as_of,
            forecast_method=request.forecast_method,
            ewma_alpha=request.ewma_alpha,
        )
        requirements.append(_req_to_schema(req))

    # Sort by risk urgency descending
    requirements.sort(key=lambda r: _risk_rank(r.risk_category), reverse=True)

    return ReplenishmentResponse(
        generated_at=datetime.utcnow(),
        product_id=request.product_id,
        destination_id=request.destination_id,
        warehouses_evaluated=wh_codes,
        requirements=requirements,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/replenishment/summary  — batch across all pairs
# ---------------------------------------------------------------------------

@router.post("/summary", response_model=ReplenishmentSummaryResponse, status_code=200)
def get_replenishment_summary(
    request: ReplenishmentSummaryRequest,
    db: Session = Depends(get_db),
):
    """Returns paginated replenishment requirements across product-destination pairs.

    Evaluates all active routes per destination (or filtered subset).
    For each destination, uses the best (minimum lead time) warehouse route.

    Large datasets: use limit/offset for pagination.
    """
    as_of: date = request.as_of_date or datetime.utcnow().date()

    # ------------------------------------------------------------------
    # 1. Fetch entities (filtered)
    # ------------------------------------------------------------------
    prod_query = db.query(Product)
    if request.product_id:
        prod_query = prod_query.filter(Product.id == request.product_id)
    products = prod_query.all()

    dst_query = db.query(Destination)
    if request.destination_id:
        dst_query = dst_query.filter(Destination.id == request.destination_id)
    destinations = dst_query.all()

    if not products:
        raise HTTPException(400, "No products found for the specified filter.")
    if not destinations:
        raise HTTPException(400, "No destinations found for the specified filter.")

    # ------------------------------------------------------------------
    # 2. Fetch routes
    # ------------------------------------------------------------------
    route_q = (
        db.query(Route, Warehouse.code.label("wh_code"))
        .join(Warehouse, Route.origin_warehouse_id == Warehouse.id)
        .filter(Route.is_active == True)
    )
    if request.warehouse_id:
        route_q = route_q.filter(Route.origin_warehouse_id == request.warehouse_id)

    all_routes = [
        {
            "id": r.id,
            "origin_warehouse_id": r.origin_warehouse_id,
            "destination_id": r.destination_id,
            "origin_warehouse_code": wh_code,
            "destination_code": "",   # filled below
            "lead_time_days": r.lead_time_days,
            "unit_transport_cost": r.unit_transport_cost,
            "is_active": r.is_active,
        }
        for r, wh_code in route_q.all()
    ]

    # Fill destination codes
    dst_id_to_code = {d.id: d.code for d in destinations}
    dst_id_to_name = {d.id: d.name for d in destinations}
    for r in all_routes:
        r["destination_code"] = dst_id_to_code.get(r["destination_id"], "")

    # ------------------------------------------------------------------
    # 3. Batch-fetch demand history (single query)
    # ------------------------------------------------------------------
    prod_ids = [p.id for p in products]
    dst_ids = [d.id for d in destinations]

    demand_rows_db = (
        db.query(DailyDemandHistory)
        .filter(
            DailyDemandHistory.product_id.in_(prod_ids),
            DailyDemandHistory.destination_id.in_(dst_ids),
        )
        .order_by(DailyDemandHistory.demand_date.asc())
        .all()
    )

    row_index: Dict = defaultdict(list)
    for r in demand_rows_db:
        row_index[(r.destination_id, r.product_id)].append({
            "demand_date": r.demand_date,
            "quantity_demanded": r.quantity_demanded,
            "quantity_sold": r.quantity_sold,
            "is_simulated": r.is_simulated,
        })

    # ------------------------------------------------------------------
    # 4. Evaluate each pair — pick best route per destination
    # ------------------------------------------------------------------
    ss_cfg = SafetyStockConfig(
        service_level_z=request.safety_stock_config.service_level_z,
        fallback_factor=request.safety_stock_config.fallback_factor,
        min_safety_stock_units=request.safety_stock_config.min_safety_stock_units,
    )

    # Group routes by destination for quick lookup
    routes_by_dst: Dict[int, List] = defaultdict(list)
    for r in all_routes:
        routes_by_dst[r["destination_id"]].append(r)

    wh_codes_seen: Set[str] = set()
    all_requirements: List[ReplenishmentRequirementSchema] = []

    for dest in destinations:
        dest_routes = routes_by_dst.get(dest.id, [])
        if not dest_routes:
            continue

        # Pick best warehouse per destination (min lead time)
        best_wh_code: Optional[str] = None
        min_lt = float("inf")
        for r in dest_routes:
            if r["lead_time_days"] < min_lt:
                min_lt = r["lead_time_days"]
                best_wh_code = r["origin_warehouse_code"]

        if best_wh_code is None:
            continue
        wh_codes_seen.add(best_wh_code)

        for prod in products:
            demand_rows = row_index[(dest.id, prod.id)]
            req = calculate_replenishment(
                product_id=prod.id,
                product_sku=prod.sku,
                product_name=prod.name,
                destination_id=dest.id,
                destination_code=dest.code,
                destination_name=dest.name,
                demand_history_rows=demand_rows,
                available_routes=dest_routes,
                warehouse_code=best_wh_code,
                ss_config=ss_cfg,
                as_of_date=as_of,
                forecast_method=request.forecast_method,
                ewma_alpha=request.ewma_alpha,
            )
            schema = _req_to_schema(req)

            # Apply risk filter
            if request.risk_filter:
                if _risk_rank(schema.risk_category) < _risk_rank(request.risk_filter):
                    continue

            all_requirements.append(schema)

    # Sort by risk descending, then destination code
    all_requirements.sort(
        key=lambda r: (-_risk_rank(r.risk_category), r.destination_code, r.product_sku)
    )

    # ------------------------------------------------------------------
    # 5. Aggregate stats
    # ------------------------------------------------------------------
    total = len(all_requirements)
    paged = all_requirements[request.offset: request.offset + request.limit]

    risk_counts = {RISK_CRITICAL: 0, RISK_HIGH: 0, RISK_MODERATE: 0,
                   RISK_LOW: 0, RISK_INSUFFICIENT_DATA: 0}
    total_qty = 0
    for r in all_requirements:
        risk_counts[r.risk_category] = risk_counts.get(r.risk_category, 0) + 1
        total_qty += r.replenishment_qty

    return ReplenishmentSummaryResponse(
        generated_at=datetime.utcnow(),
        total=total,
        limit=request.limit,
        offset=request.offset,
        warehouses_evaluated=sorted(wh_codes_seen),
        as_of_date=as_of,
        requirements=paged,
        total_replenishment_units=total_qty,
        critical_count=risk_counts[RISK_CRITICAL],
        high_count=risk_counts[RISK_HIGH],
        moderate_count=risk_counts[RISK_MODERATE],
        low_count=risk_counts[RISK_LOW],
        insufficient_data_count=risk_counts[RISK_INSUFFICIENT_DATA],
        caveats=OPTIMIZER_CAVEATS,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/replenishment/optimizer-contract  — optimizer integration
# ---------------------------------------------------------------------------

@router.get("/optimizer-contract", response_model=OptimizerContractResponse)
def get_optimizer_contract(
    warehouse_id: Optional[int] = Query(None, description="Filter to a specific warehouse."),
    product_id: Optional[int] = Query(None, description="Filter to a specific product."),
    destination_id: Optional[int] = Query(None, description="Filter to a specific destination."),
    risk_filter: Optional[str] = Query(
        None,
        description="Minimum risk level: Critical, High, Moderate.",
    ),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Returns the optimizer integration contract for all replenishment requirements.

    The contract exposes exactly the fields the OR-Tools engine needs:
    product/destination IDs, replenishment quantity, lead-time demand,
    safety stock, projected position, and risk category.

    The optimizer MUST NOT treat replenishment_qty as available supply.
    """
    # Re-use summary logic with max limit
    summary_request = ReplenishmentSummaryRequest(
        warehouse_id=warehouse_id,
        product_id=product_id,
        destination_id=destination_id,
        risk_filter=risk_filter,
        limit=limit,
        offset=0,
    )

    summary = get_replenishment_summary(summary_request, db)

    items: List[OptimizerContractItem] = []
    for r in summary.requirements:
        items.append(OptimizerContractItem(
            product_id=r.product_id,
            product_sku=r.product_sku,
            destination_id=r.destination_id,
            destination_code=r.destination_code,
            replenishment_qty=r.replenishment_qty,
            gross_replenishment=r.gross_replenishment,
            lead_time_demand=r.lead_time_demand,
            daily_mean_demand=r.daily_mean_demand,
            lead_time_days=r.lead_time_days,
            safety_stock_units=r.safety_stock.safety_stock_int,
            safety_stock_method=r.safety_stock.method_used,
            projected_position=r.projected_position,
            destination_stock_tracked=False,
            risk_category=r.risk_category,
            warnings=r.warnings,
            history_used=r.history_observations_used,
            forecast_method=r.forecast_method,
        ))

    return OptimizerContractResponse(
        generated_at=datetime.utcnow(),
        n_items=len(items),
        caveats=OPTIMIZER_CAVEATS,
        items=items,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/replenishment/risk-rules  — self-documenting endpoint
# ---------------------------------------------------------------------------

@router.get("/risk-rules")
def get_risk_rules():
    """Returns the documented risk-category assignment rules.

    These are heuristic bands, NOT calibrated stockout probabilities.
    """
    return {
        "risk_category_rules": {
            "Critical": "cover_days == 0 (already out of stock at destination)",
            "High": "0 < cover_days <= lead_time_days (will stock out before replenishment arrives)",
            "Moderate": "lead_time_days < cover_days <= lead_time_days + safety_stock_days",
            "Low": "cover_days > lead_time_days + safety_stock_days",
            "InsufficientData": "daily_mean_demand == 0 or demand history unavailable",
        },
        "important_notes": [
            "These categories are NOT calibrated stockout probabilities.",
            "They are heuristic risk bands based on cover-day comparison.",
            "Achieving a specific service level requires σ_d to match the normal distribution assumption.",
            "All metrics depend on forecast accuracy; forecast uncertainty is not propagated.",
        ],
        "safety_stock_formula": "SS = z × σ_d × √L",
        "threshold_formula": "threshold = lead_time_demand + safety_stock",
        "replenishment_formula": "replenishment_qty = ceil(max(0, threshold - projected_position))",
        "current_database_gaps": {
            "GAP-1": "DestinationInventory table not yet created. projected_position = 0.",
            "GAP-2": "ConfirmedDispatch / InTransit table not yet created. incoming_qty = 0.",
        },
    }
