"""Planning and Optimization route handlers."""

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import (
    DailyDemandHistory,
    DatasetVersion,
    Destination,
    InventoryItem,
    PlanningRun,
    Product,
    Route,
    ShipmentRecommendation,
    Warehouse,
)
from app.schemas.plan import (
    BaselineComparisonSchema,
    OptimizationParameters,
    PlanRequest,
    PlanResponse,
    PlanningRunListItem,
    PlanningRunListResponse,
    PlanSummaryMetrics,
    ShipmentSchema,
    StockoutRiskAlert,
    UnmetDemandSchema,
    VerificationSummarySchema,
)
from app.engine.forecast.forecaster import BaselineDemandForecaster
from app.engine.position.inventory_position import InventoryPositionAnalyzer
from app.engine.position.replenishment import calculate_replenishment
from app.engine.position.safety_stock import SafetyStockConfig
from app.engine.validation.validator import DistributionPlanValidator
from app.engine.optimize.solver import DistributionSolver
from app.engine.verify.verifier import SolutionVerifier
from app.engine.explain.explainer import DistributionDecisionExplainer

router = APIRouter(prefix="/planning", tags=["Planning"])


@router.post("/run", response_model=PlanResponse)
@router.post("/optimize", response_model=PlanResponse)
def execute_planning_run(request: PlanRequest, db: Session = Depends(get_db)):
    """Executes a constraint-aware FMCG distribution planning run.

    Enforces:
      - Warehouse usable stock bounds (excluding expired, quarantined, and reserved units).
      - Destination-product demand bounds with explicit unmet-demand accounting.
      - Active route eligibility (inactive routes rejected).
      - Warehouse dispatch and destination receiving throughput limits.
      - Configurable lead-time cutoffs.
      - Multi-profile formulations: Cost-First, Service-First (staged/lexicographic), Balanced.
      - Independent 12-invariant solution verification.
      - Comparison against deterministic constraint-aware greedy baseline.

    Strictly preserves source inventory without mutating physical batches.
    """
    now = datetime.utcnow()
    as_of = request.as_of_date or now.date()

    # 1. Fetch active or specified dataset version
    if request.dataset_version_id:
        ds_ver = db.query(DatasetVersion).filter(DatasetVersion.id == request.dataset_version_id).first()
    else:
        ds_ver = (
            db.query(DatasetVersion)
            .filter(DatasetVersion.is_active == True)
            .order_by(DatasetVersion.id.desc())
            .first()
        )

    if not ds_ver:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dataset version available. Run seed script first.",
        )

    # 2. Fetch network entities
    db_warehouses = db.query(Warehouse).all()
    warehouses = [
        {
            "id": w.id,
            "code": w.code,
            "name": w.name,
            "capacity_units": w.capacity_units,
            "daily_dispatch_capacity_units": w.daily_dispatch_capacity_units,
            "latitude": w.latitude,
            "longitude": w.longitude,
        }
        for w in db_warehouses
    ]

    db_destinations = db.query(Destination).all()
    destinations = [
        {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            "channel_type": d.channel_type,
            "daily_receiving_capacity_units": d.daily_receiving_capacity_units,
            "latitude": d.latitude,
            "longitude": d.longitude,
        }
        for d in db_destinations
    ]

    db_products = db.query(Product).all()
    products = [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "shelf_life_days": p.shelf_life_days,
            "unit_cost": p.unit_cost,
            "unit_price": p.unit_price,
            "holding_cost_per_day": p.holding_cost_per_day,
            "lost_sales_penalty": p.lost_sales_penalty,
        }
        for p in db_products
    ]

    # Fetch active routes
    route_records = (
        db.query(Route, Warehouse.code.label("wh_code"), Destination.code.label("dst_code"))
        .join(Warehouse, Route.origin_warehouse_id == Warehouse.id)
        .join(Destination, Route.destination_id == Destination.id)
        .all()
    )
    routes_dicts = [
        {
            "id": r.id,
            "origin_warehouse_id": r.origin_warehouse_id,
            "destination_id": r.destination_id,
            "origin_warehouse_code": wh_code,
            "source_warehouse_code": wh_code,
            "destination_code": dst_code,
            "unit_transport_cost": r.unit_transport_cost,
            "lead_time_days": r.lead_time_days,
            "distance_km": r.distance_km,
            "is_active": r.is_active,
        }
        for r, wh_code, dst_code in route_records
    ]

    # Fetch inventory items
    inv_records = (
        db.query(InventoryItem, Warehouse.code, Product.sku)
        .join(Warehouse, InventoryItem.warehouse_id == Warehouse.id)
        .join(Product, InventoryItem.product_id == Product.id)
        .filter(InventoryItem.dataset_version_id == ds_ver.id)
        .all()
    )
    inventory_items = [
        {
            "warehouse_code": wh_code,
            "product_sku": prod_sku,
            "batch_lot": item.batch_lot,
            "on_hand_units": item.on_hand_units,
            "reserved_units": item.reserved_units,
            "unit_cost": item.unit_cost,
            "expiry_date": item.expiry_date,
            "received_date": item.received_date,
            "batch_status": item.batch_status,
        }
        for item, wh_code, prod_sku in inv_records
    ]

    # 3. Determine demand requirements
    data_quality_warnings: List[str] = []
    opt_profile = (
        request.optimization_profile
        or request.parameters.profile
        or "balanced"
    ).lower()
    lead_time_cutoff = (
        request.max_lead_time_days
        if request.max_lead_time_days is not None
        else request.parameters.max_lead_time_days
    )

    demand_targets: List[Dict[str, Any]] = []
    stockout_alerts_raw: List[Dict[str, Any]] = []

    # Check if demand history exists in DB
    has_history = db.query(DailyDemandHistory).first() is not None

    if request.parameters.use_replenishment_engine and has_history:
        # Load empirical history grouped by (destination_id, product_id)
        history_rows = (
            db.query(DailyDemandHistory)
            .filter(DailyDemandHistory.demand_date <= datetime.combine(as_of, datetime.min.time()))
            .order_by(DailyDemandHistory.demand_date.asc())
            .all()
        )
        history_by_pair = defaultdict(list)
        for h in history_rows:
            history_by_pair[(h.destination_id, h.product_id)].append({
                "demand_date": h.demand_date,
                "quantity_demanded": h.quantity_demanded,
                "quantity_sold": h.quantity_sold,
                "is_simulated": h.is_simulated,
            })

        ss_cfg = SafetyStockConfig(
            service_level_z=request.parameters.service_level_z,
            fallback_factor=0.25,
            min_safety_stock_units=0.0,
        )

        routes_by_dst = defaultdict(list)
        for r in routes_dicts:
            if r.get("destination_id"):
                routes_by_dst[r["destination_id"]].append(r)

        for d in db_destinations:
            dest_routes = routes_by_dst.get(d.id, [])
            best_wh_code = None
            min_lt = float("inf")
            for r in dest_routes:
                if r.get("is_active", True) and r["lead_time_days"] < min_lt:
                    min_lt = r["lead_time_days"]
                    best_wh_code = r["origin_warehouse_code"]
            if not best_wh_code and dest_routes:
                best_wh_code = dest_routes[0]["origin_warehouse_code"]
            if not best_wh_code and warehouses:
                best_wh_code = warehouses[0]["code"]

            for p in db_products:
                dh_rows = history_by_pair.get((d.id, p.id), [])
                if not dh_rows:
                    continue

                # Calculate replenishment requirement
                replen_res = calculate_replenishment(
                    product_id=p.id,
                    product_sku=p.sku,
                    product_name=p.name,
                    destination_id=d.id,
                    destination_code=d.code,
                    destination_name=d.name,
                    demand_history_rows=dh_rows,
                    available_routes=routes_dicts,
                    warehouse_code=best_wh_code,
                    ss_config=ss_cfg,
                    as_of_date=as_of,
                    forecast_method="ewma",
                    ewma_alpha=request.parameters.ewma_alpha,
                )

                demand_targets.append({
                    "destination_code": d.code,
                    "destination_name": d.name,
                    "sku": p.sku,
                    "product_name": p.name,
                    "forecasted_units": replen_res.replenishment_qty,
                    "units": replen_res.replenishment_qty,
                    "risk_category": replen_res.risk_category,
                    "daily_mean_demand": replen_res.daily_mean_demand,
                    "lead_time_demand": replen_res.lead_time_demand,
                    "safety_stock_units": replen_res.safety_stock.safety_stock_int,
                })

                if replen_res.risk_category in ("Critical", "High", "Moderate"):
                    stockout_alerts_raw.append({
                        "destination_code": d.code,
                        "destination_name": d.name,
                        "product_sku": p.sku,
                        "current_inventory_days": replen_res.cover_days,
                        "forecasted_daily_demand": replen_res.daily_mean_demand,
                        "risk_level": replen_res.risk_category,
                    })

        forecast_id = f"REPLEN-{ds_ver.version_tag}-{as_of.isoformat()}"
    else:
        # Fallback to BaselineDemandForecaster
        forecaster = BaselineDemandForecaster(seed=ds_ver.random_seed)
        raw_demands = forecaster.forecast_demand(
            destinations, products, horizon_days=request.forecast_horizon_days
        )
        for dt in raw_demands:
            demand_targets.append({
                "destination_code": dt["destination_code"],
                "destination_name": dt.get("destination_name", dt["destination_code"]),
                "sku": dt["sku"],
                "product_name": dt.get("product_name", dt["sku"]),
                "forecasted_units": dt["forecasted_units"],
                "units": dt["forecasted_units"],
                "risk_category": "Moderate",
            })
        stockout_alerts_raw = InventoryPositionAnalyzer.identify_stockout_risks(demand_targets)
        forecast_id = f"FCST-{ds_ver.version_tag}-H{request.forecast_horizon_days}D"

    # 4. Strict inventory accounting: only usable unexpired inventory counts as supply
    available_supply = InventoryPositionAnalyzer.calculate_warehouse_available_stock(
        inventory_items, as_of_date=now, require_usable=True
    )

    # 5. Validation
    is_valid, validation_errors = DistributionPlanValidator.validate_supply_and_demand(
        warehouses, inventory_items, demand_targets, as_of_date=now
    )
    if validation_errors:
        data_quality_warnings.extend(validation_errors)

    # 6. Optimization solver
    solver = DistributionSolver(
        transport_weight=request.parameters.transport_weight,
        stockout_penalty_weight=request.parameters.stockout_penalty_weight,
        expiry_risk_weight=request.parameters.expiry_risk_weight,
        max_solver_time_seconds=request.parameters.max_solver_time_seconds,
        profile=opt_profile,
        max_lead_time_days=lead_time_cutoff,
    )

    solver_result = solver.solve_distribution_plan(
        warehouses=warehouses,
        destinations=destinations,
        products=products,
        available_supply=available_supply,
        demand_targets=demand_targets,
        routes=routes_dicts,
        inventory_items=inventory_items,
        profile=opt_profile,
        max_lead_time_days=lead_time_cutoff,
    )

    raw_shipments = solver_result.get("shipments", [])
    raw_unmet = solver_result.get("unmet_demands", [])

    # 7. Independent Solution Verification
    verification_report = SolutionVerifier.verify_comprehensive(
        shipments=raw_shipments,
        available_supply=available_supply,
        demand_targets=demand_targets,
        warehouses=warehouses,
        destinations=destinations,
        routes=routes_dicts,
        max_lead_time_days=lead_time_cutoff,
        inventory_items=inventory_items,
        unmet_demands=raw_unmet,
        reported_transport_cost=solver_result.get("total_transport_cost"),
        as_of_date=as_of,
    )

    # 8. Explainability
    explained_shipments = DistributionDecisionExplainer.enrich_shipments_with_reasoning(
        shipments=raw_shipments,
        available_supply=available_supply,
        routes=routes_dicts,
        demand_targets=demand_targets,
    )

    # 9. Record planning run in database
    run_code = f"RUN-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    plan_run = PlanningRun(
        run_code=run_code,
        dataset_version_id=ds_ver.id,
        forecast_identifier=forecast_id,
        optimization_parameters={
            **request.parameters.model_dump(),
            "profile": opt_profile,
            "max_lead_time_days": lead_time_cutoff,
        },
        solver_status=solver_result.get("solver_status", "UNKNOWN"),
        total_transport_cost=solver_result.get("total_transport_cost", 0.0),
        total_shipped_units=solver_result.get("total_units", 0),
        stockout_risk_count=len(stockout_alerts_raw),
        status="FEASIBLE" if verification_report.is_feasible else "VIOLATIONS_DETECTED",
        created_at=now,
    )
    db.add(plan_run)
    db.commit()
    db.refresh(plan_run)

    # Save shipment recommendations associated with run
    wh_id_map = {w["code"]: w["id"] for w in warehouses}
    dst_id_map = {d["code"]: d["id"] for d in destinations}
    prod_id_map = {p["sku"]: p["id"] for p in products}

    rec_objects = []
    for s in explained_shipments:
        w_id = wh_id_map.get(s["source_warehouse_code"])
        d_id = dst_id_map.get(s["destination_code"])
        p_id = prod_id_map.get(s["product_sku"])
        if w_id and d_id and p_id:
            rec_objects.append(
                ShipmentRecommendation(
                    planning_run_id=plan_run.id,
                    source_warehouse_id=w_id,
                    destination_id=d_id,
                    product_id=p_id,
                    recommended_units=s["recommended_units"],
                    unit_transport_cost=s["unit_transport_cost"],
                    total_transport_cost=s["total_transport_cost"],
                    estimated_expiry_risk_pct=s.get("estimated_expiry_risk_pct", 0.0),
                    priority_score=1.0,
                    reasoning=s.get("reasoning"),
                )
            )

    if rec_objects:
        db.bulk_save_objects(rec_objects)
        db.commit()

    # 10. Assemble Response Objects
    metrics = PlanSummaryMetrics(
        total_shipped_units=solver_result.get("total_units", 0),
        total_transport_cost=solver_result.get("total_transport_cost", 0.0),
        avg_expiry_risk_pct=0.0,
        stockouts_prevented=max(0, len(stockout_alerts_raw) - len(raw_unmet)),
        destinations_at_risk=len(set(a["destination_code"] for a in stockout_alerts_raw)),
        total_demanded_units=solver_result.get("total_demanded_units", 0),
        total_unmet_units=solver_result.get("total_unmet_units", 0),
        fulfillment_rate=solver_result.get("fulfillment_rate", 1.0),
        solver_runtime_seconds=solver_result.get("solver_runtime_seconds", 0.0),
    )

    stockout_alerts = [
        StockoutRiskAlert(
            destination_code=a["destination_code"],
            destination_name=a["destination_name"],
            product_sku=a["product_sku"],
            current_inventory_days=a["current_inventory_days"],
            forecasted_daily_demand=a["forecasted_daily_demand"],
            risk_level=a["risk_level"],
        )
        for a in stockout_alerts_raw[:25]
    ]

    shipment_schemas = [
        ShipmentSchema(
            id=idx + 1,
            source_warehouse_code=s["source_warehouse_code"],
            destination_code=s["destination_code"],
            destination_name=s["destination_name"],
            product_sku=s["product_sku"],
            product_name=s["product_name"],
            recommended_units=s["recommended_units"],
            unit_transport_cost=s["unit_transport_cost"],
            total_transport_cost=s["total_transport_cost"],
            estimated_expiry_risk_pct=s.get("estimated_expiry_risk_pct", 0.0),
            lead_time_days=s.get("lead_time_days", 1.0),
            reasoning=s.get("reasoning"),
        )
        for idx, s in enumerate(explained_shipments)
    ]

    unmet_schemas = [
        UnmetDemandSchema(
            destination_code=u["destination_code"],
            destination_name=u["destination_name"],
            product_sku=u["product_sku"],
            product_name=u["product_name"],
            demanded_units=u["demanded_units"],
            fulfilled_units=u["fulfilled_units"],
            unmet_units=u["unmet_units"],
            risk_category=u["risk_category"],
        )
        for u in raw_unmet
    ]

    baseline_comp = None
    if solver_result.get("baseline_comparison"):
        bc = solver_result["baseline_comparison"]
        baseline_comp = BaselineComparisonSchema(
            baseline_total_units=bc["baseline_total_units"],
            baseline_total_cost=bc["baseline_total_cost"],
            baseline_unmet_units=bc["baseline_unmet_units"],
            baseline_fulfillment_rate=bc["baseline_fulfillment_rate"],
            optimized_total_units=bc["optimized_total_units"],
            optimized_total_cost=bc["optimized_total_cost"],
            optimized_unmet_units=bc["optimized_unmet_units"],
            optimized_fulfillment_rate=bc["optimized_fulfillment_rate"],
            units_difference=bc["units_difference"],
            cost_difference=bc["cost_difference"],
            fulfillment_rate_difference=bc["fulfillment_rate_difference"],
        )

    verification_summary = VerificationSummarySchema(
        is_feasible=verification_report.is_feasible,
        violations_count=len(verification_report.violations),
        violations=verification_report.violations[:10],
        recalculated_cost=verification_report.recalculated_cost,
        recalculated_units=verification_report.recalculated_units,
        recalculated_fulfilled=verification_report.recalculated_fulfilled,
        recalculated_unmet=verification_report.recalculated_unmet,
    )

    return PlanResponse(
        run_code=run_code,
        dataset_version=ds_ver.version_tag,
        forecast_identifier=forecast_id,
        solver_status=solver_result.get("solver_status", "UNKNOWN"),
        created_at=plan_run.created_at,
        metrics=metrics,
        shipments=shipment_schemas,
        stockout_risks=stockout_alerts,
        unmet_demands=unmet_schemas,
        baseline_comparison=baseline_comp,
        verification=verification_summary,
        data_quality_warnings=data_quality_warnings,
        optimization_profile=opt_profile,
    )


@router.get("/runs", response_model=PlanningRunListResponse)
def list_planning_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lists historical planning runs."""
    total = db.query(PlanningRun).count()
    runs = db.query(PlanningRun).order_by(PlanningRun.id.desc()).offset(offset).limit(limit).all()
    return PlanningRunListResponse(
        total=total,
        limit=limit,
        offset=offset,
        runs=[PlanningRunListItem.model_validate(r) for r in runs],
    )


@router.get("/runs/{run_code}", response_model=PlanResponse)
def get_planning_run(run_code: str, db: Session = Depends(get_db)):
    """Retrieves an existing planning run and its persisted shipment recommendations."""
    plan_run = db.query(PlanningRun).filter(PlanningRun.run_code == run_code).first()
    if not plan_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Planning run with code {run_code} not found.",
        )

    ds_ver = db.query(DatasetVersion).filter(DatasetVersion.id == plan_run.dataset_version_id).first()

    shipment_records = (
        db.query(ShipmentRecommendation, Warehouse.code, Destination.code, Destination.name, Product.sku, Product.name)
        .join(Warehouse, ShipmentRecommendation.source_warehouse_id == Warehouse.id)
        .join(Destination, ShipmentRecommendation.destination_id == Destination.id)
        .join(Product, ShipmentRecommendation.product_id == Product.id)
        .filter(ShipmentRecommendation.planning_run_id == plan_run.id)
        .all()
    )

    shipments = [
        ShipmentSchema(
            id=s.id,
            source_warehouse_code=wh_code,
            destination_code=dst_code,
            destination_name=dst_name,
            product_sku=prod_sku,
            product_name=prod_name,
            recommended_units=s.recommended_units,
            unit_transport_cost=s.unit_transport_cost,
            total_transport_cost=s.total_transport_cost,
            estimated_expiry_risk_pct=s.estimated_expiry_risk_pct,
            reasoning=s.reasoning,
        )
        for s, wh_code, dst_code, dst_name, prod_sku, prod_name in shipment_records
    ]

    metrics = PlanSummaryMetrics(
        total_shipped_units=plan_run.total_shipped_units,
        total_transport_cost=plan_run.total_transport_cost,
        avg_expiry_risk_pct=0.0,
        stockouts_prevented=max(0, plan_run.stockout_risk_count - 2),
        destinations_at_risk=plan_run.stockout_risk_count,
    )

    profile_used = "balanced"
    if isinstance(plan_run.optimization_parameters, dict):
        profile_used = plan_run.optimization_parameters.get("profile", "balanced")

    return PlanResponse(
        run_code=plan_run.run_code,
        dataset_version=ds_ver.version_tag if ds_ver else "unknown",
        forecast_identifier=plan_run.forecast_identifier,
        solver_status=plan_run.solver_status,
        created_at=plan_run.created_at,
        metrics=metrics,
        shipments=shipments,
        stockout_risks=[],
        unmet_demands=[],
        baseline_comparison=None,
        verification=None,
        data_quality_warnings=[],
        optimization_profile=profile_used,
    )
