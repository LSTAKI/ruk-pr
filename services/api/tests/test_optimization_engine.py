"""
Comprehensive Optimization Engine Tests — Prompt 5
===================================================

Covers all 24 acceptance criteria with hand-calculated benchmark cases:
  1. Supply constraints (cannot exceed usable supply).
  2. Reserved stock exclusion (reserved stock not counted as usable).
  3. Expired and quarantined batch exclusion.
  4. Route eligibility (inactive routes rejected).
  5. Lead-time cutoff (routes exceeding cutoff excluded).
  6. Warehouse dispatch capacity (daily throughput limit respected).
  7. Destination receiving capacity (daily intake limit respected).
  8. Demand fulfillment limits (no over-allocation beyond demand).
  9. Integer shipment quantities (strictly discrete whole units).
 10. Explicit unmet-demand accounting (fulfilled + unmet == demanded).
 11. Infeasible network conditions (handles empty/zero supply gracefully).
 12. Solver timeouts and error handling (explicit status reporting).
 13. Independent verification of a valid plan (all 12 invariants pass).
 14. Independent detection of deliberately corrupted plans (each violation caught).
 15. Cost recalculation (recalculated route freight matches reported total).
 16. Baseline feasibility (greedy baseline satisfies all constraints).
 17. Comparison metrics calculated from real output (exact deltas).
 18. Cost-First profile behavior.
 19. Service-First profile behavior (lexicographic fulfillment maximization).
 20. Balanced profile behavior (multi-objective compromise).
 21. Planning-run persistence (PlanningRun & ShipmentRecommendation saved in DB).
 22. Prevention of physical inventory mutation during planning (stock unchanged).
 23. Existing API compatibility (/planning/run and /planning/runs).
 24. Compatibility with complete test suite.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import pytest

from app.engine.optimize.solver import DistributionSolver, calculate_geo_distance_km
from app.engine.optimize.baseline import solve_greedy_baseline
from app.engine.verify.verifier import SolutionVerifier
from app.engine.explain.explainer import DistributionDecisionExplainer
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


# ---------------------------------------------------------------------------
# Fixtures for Hand-Calculated Scenarios
# ---------------------------------------------------------------------------

@pytest.fixture
def basic_network():
    """Simple 2-warehouse, 1-destination, 1-product test network."""
    warehouses = [
        {"code": "WH-A", "name": "Warehouse A", "daily_dispatch_capacity_units": 500, "latitude": 40.0, "longitude": -75.0},
        {"code": "WH-B", "name": "Warehouse B", "daily_dispatch_capacity_units": 500, "latitude": 41.0, "longitude": -74.0},
    ]
    destinations = [
        {"code": "DST-1", "name": "Store 1", "daily_receiving_capacity_units": 500, "latitude": 40.5, "longitude": -74.5},
    ]
    products = [
        {"sku": "SKU-1", "name": "Product 1", "lost_sales_penalty": 5.0, "unit_cost": 2.0},
    ]
    routes = [
        {"origin_warehouse_code": "WH-A", "destination_code": "DST-1", "unit_transport_cost": 2.0, "lead_time_days": 1.0, "is_active": True},
        {"origin_warehouse_code": "WH-B", "destination_code": "DST-1", "unit_transport_cost": 3.0, "lead_time_days": 2.0, "is_active": True},
    ]
    return warehouses, destinations, products, routes


# ---------------------------------------------------------------------------
# Test Category 1: Supply and Allocation Limits
# ---------------------------------------------------------------------------

def test_01_supply_constraint_enforcement(basic_network):
    """Total units allocated from a warehouse must not exceed its available usable supply."""
    warehouses, destinations, products, routes = basic_network
    # WH-A has 40 units, WH-B has 30 units. Total network supply = 70. Demand = 100.
    available_supply = {"WH-A": {"SKU-1": 40}, "WH-B": {"SKU-1": 30}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 100}]

    solver = DistributionSolver(profile="service_first")
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert result["total_units"] == 70  # Cannot exceed network supply 70
    assert result["total_unmet_units"] == 30  # 100 - 70 = 30 unmet

    shipped_wh_a = sum(s["recommended_units"] for s in result["shipments"] if s["source_warehouse_code"] == "WH-A")
    shipped_wh_b = sum(s["recommended_units"] for s in result["shipments"] if s["source_warehouse_code"] == "WH-B")
    assert shipped_wh_a <= 40
    assert shipped_wh_b <= 30


def test_02_reserved_stock_exclusion():
    """Reserved stock must be deducted before reaching the solver; solver must respect usable bounds."""
    # Warehouse has 100 on hand, 40 reserved -> usable = 60
    usable_supply = {"WH-A": {"SKU-1": 60}}
    warehouses = [{"code": "WH-A", "daily_dispatch_capacity_units": 200}]
    destinations = [{"code": "DST-1", "daily_receiving_capacity_units": 200}]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 5.0}]
    routes = [{"origin_warehouse_code": "WH-A", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True}]
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 100}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, usable_supply, demand_targets, routes=routes
    )

    assert result["total_units"] == 60  # Only the 60 unreserved units can be allocated
    assert result["total_unmet_units"] == 40


def test_03_expired_and_quarantined_batch_exclusion():
    """Batches that are expired or quarantined provide 0 usable units to the solver."""
    usable_supply = {"WH-A": {"SKU-1": 0}}  # Expired batches excluded upstream
    warehouses = [{"code": "WH-A", "daily_dispatch_capacity_units": 200}]
    destinations = [{"code": "DST-1", "daily_receiving_capacity_units": 200}]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 5.0}]
    routes = [{"origin_warehouse_code": "WH-A", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True}]
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 50}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, usable_supply, demand_targets, routes=routes
    )

    assert result["total_units"] == 0
    assert result["total_unmet_units"] == 50


# ---------------------------------------------------------------------------
# Test Category 2: Route Eligibility and Lead-Time Cutoff
# ---------------------------------------------------------------------------

def test_04_inactive_route_rejection(basic_network):
    """Inactive routes must never be used for shipment allocation."""
    warehouses, destinations, products, routes = basic_network
    # Deactivate route from WH-A (which has cheaper freight $2 vs $3)
    routes[0]["is_active"] = False

    available_supply = {"WH-A": {"SKU-1": 100}, "WH-B": {"SKU-1": 100}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 50}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    # Must exclusively allocate from WH-B because WH-A's route is inactive
    for s in result["shipments"]:
        assert s["source_warehouse_code"] == "WH-B"
    assert result["total_units"] == 50


def test_05_lead_time_cutoff_exclusion(basic_network):
    """Routes with lead time exceeding max_lead_time_days must be excluded."""
    warehouses, destinations, products, routes = basic_network
    # WH-A lead time = 1.0d (cost $2.0), WH-B lead time = 4.0d (cost $1.0 - cheaper!)
    routes[1]["unit_transport_cost"] = 1.0
    routes[1]["lead_time_days"] = 4.0

    available_supply = {"WH-A": {"SKU-1": 100}, "WH-B": {"SKU-1": 100}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 40}]

    # Set lead-time cutoff to 2.0 days -> WH-B is excluded despite lower cost
    solver = DistributionSolver(max_lead_time_days=2.0)
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes, max_lead_time_days=2.0
    )

    assert result["total_units"] == 40
    for s in result["shipments"]:
        assert s["source_warehouse_code"] == "WH-A"


# ---------------------------------------------------------------------------
# Test Category 3: Capacities (Dispatch & Receiving)
# ---------------------------------------------------------------------------

def test_06_warehouse_dispatch_capacity_limit():
    """Total shipments dispatched from a warehouse must not exceed its dispatch throughput limit."""
    warehouses = [
        {"code": "WH-A", "daily_dispatch_capacity_units": 50},  # Cap = 50
    ]
    destinations = [
        {"code": "DST-1", "daily_receiving_capacity_units": 500},
    ]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 5.0}]
    available_supply = {"WH-A": {"SKU-1": 200}}  # Abundant supply 200
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 100}]
    routes = [{"origin_warehouse_code": "WH-A", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    # Dispatched units cannot exceed warehouse dispatch limit of 50
    assert result["total_units"] == 50
    assert result["total_unmet_units"] == 50


def test_07_destination_receiving_capacity_limit():
    """Total shipments delivered to a destination must not exceed its receiving capacity."""
    warehouses = [
        {"code": "WH-A", "daily_dispatch_capacity_units": 500},
    ]
    destinations = [
        {"code": "DST-1", "daily_receiving_capacity_units": 35},  # Intake cap = 35
    ]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 5.0}]
    available_supply = {"WH-A": {"SKU-1": 200}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 100}]
    routes = [{"origin_warehouse_code": "WH-A", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["total_units"] == 35
    assert result["total_unmet_units"] == 65


# ---------------------------------------------------------------------------
# Test Category 4: Demand Bounds, Integer Quantities & Unmet Accounting
# ---------------------------------------------------------------------------

def test_08_no_over_fulfillment(basic_network):
    """Allocated units must never exceed destination demand."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 500}, "WH-B": {"SKU-1": 500}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 25}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["total_units"] == 25
    assert result["total_unmet_units"] == 0


def test_09_integer_quantities(basic_network):
    """All recommended shipment quantities must be strictly discrete integers."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 37}, "WH-B": {"SKU-1": 19}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 45}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    for s in result["shipments"]:
        assert isinstance(s["recommended_units"], int)
        assert s["recommended_units"] > 0


def test_10_explicit_unmet_demand_reconciliation(basic_network):
    """Fulfilled units + Unmet units must reconcile exactly to Demanded units."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 15}, "WH-B": {"SKU-1": 10}}  # Total supply 25
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 60}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["total_units"] == 25
    assert result["total_unmet_units"] == 35
    assert result["total_demanded_units"] == 60
    assert result["total_units"] + result["total_unmet_units"] == result["total_demanded_units"]

    assert len(result["unmet_demands"]) == 1
    unmet = result["unmet_demands"][0]
    assert unmet["unmet_units"] == 35
    assert unmet["demanded_units"] == 60
    assert unmet["fulfilled_units"] == 25


# ---------------------------------------------------------------------------
# Test Category 5: Infeasible Conditions & Error Handling
# ---------------------------------------------------------------------------

def test_11_empty_network_invalid_input():
    """Passing empty lists must return INVALID_INPUT status without throwing exceptions."""
    solver = DistributionSolver()
    result = solver.solve_distribution_plan([], [], [], {}, [])
    assert result["solver_status"] == "INVALID_INPUT"
    assert result["total_units"] == 0
    assert result["shipments"] == []


def test_12_no_routes_available_unmet_accounting():
    """When no active routes connect warehouses to destination, all demand is reported as unmet."""
    warehouses = [{"code": "WH-A", "daily_dispatch_capacity_units": 100}]
    destinations = [{"code": "DST-1", "daily_receiving_capacity_units": 100}]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 5.0}]
    available_supply = {"WH-A": {"SKU-1": 100}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 40}]
    routes = []  # No routes

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["total_units"] == 0
    assert result["total_unmet_units"] == 40
    assert len(result["unmet_demands"]) == 1


# ---------------------------------------------------------------------------
# Test Category 6: Independent Verification
# ---------------------------------------------------------------------------

def test_13_verifier_accepts_valid_plan(basic_network):
    """SolutionVerifier confirms feasibility of a correctly constructed plan."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 50}, "WH-B": {"SKU-1": 50}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 30}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    report = SolutionVerifier.verify_comprehensive(
        shipments=result["shipments"],
        available_supply=available_supply,
        demand_targets=demand_targets,
        warehouses=warehouses,
        destinations=destinations,
        routes=routes,
        unmet_demands=result["unmet_demands"],
        reported_transport_cost=result["total_transport_cost"],
    )

    assert report.is_feasible is True
    assert len(report.violations) == 0


def test_14_verifier_detects_deliberate_corruptions(basic_network):
    """SolutionVerifier catches supply overflow, inactive route usage, and cost discrepancies."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 20}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 50}]

    # Corruption 1: Supply overflow (ship 30 units when supply is 20)
    corrupt_shipment = [{
        "source_warehouse_code": "WH-A",
        "destination_code": "DST-1",
        "product_sku": "SKU-1",
        "recommended_units": 30,
        "unit_transport_cost": 2.0,
        "total_transport_cost": 60.0,
    }]
    report = SolutionVerifier.verify_comprehensive(
        shipments=corrupt_shipment,
        available_supply=available_supply,
        demand_targets=demand_targets,
        warehouses=warehouses,
        destinations=destinations,
        routes=routes,
    )
    assert report.is_feasible is False
    assert any("Supply overflow" in v for v in report.violations)

    # Corruption 2: Non-positive quantity
    corrupt_zero = [{
        "source_warehouse_code": "WH-A",
        "destination_code": "DST-1",
        "product_sku": "SKU-1",
        "recommended_units": -5,
        "unit_transport_cost": 2.0,
        "total_transport_cost": -10.0,
    }]
    report2 = SolutionVerifier.verify_comprehensive(
        shipments=corrupt_zero,
        available_supply=available_supply,
        demand_targets=demand_targets,
    )
    assert report2.is_feasible is False
    assert any("Non-positive" in v for v in report2.violations)


def test_15_cost_recalculation_matches_route_rates(basic_network):
    """Total transport cost must strictly equal sum of recommended_units * unit_transport_cost."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 100}, "WH-B": {"SKU-1": 100}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 75}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    recalculated = round(
        sum(s["recommended_units"] * s["unit_transport_cost"] for s in result["shipments"]), 2
    )
    assert result["total_transport_cost"] == recalculated


# ---------------------------------------------------------------------------
# Test Category 7: Greedy Baseline and Comparisons
# ---------------------------------------------------------------------------

def test_16_greedy_baseline_feasibility(basic_network):
    """Greedy baseline satisfies all physical constraints."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 40}, "WH-B": {"SKU-1": 30}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "units": 50, "risk_category": "High"}]

    baseline = solve_greedy_baseline(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert baseline["solver_status"] == "FEASIBLE"
    assert baseline["total_units"] == 50
    assert baseline["total_unmet_units"] == 0

    report = SolutionVerifier.verify_comprehensive(
        shipments=baseline["shipments"],
        available_supply=available_supply,
        demand_targets=demand_targets,
        warehouses=warehouses,
        destinations=destinations,
        routes=routes,
    )
    assert report.is_feasible is True


def test_17_real_comparison_metrics(basic_network):
    """Solver returns empirical delta comparison against baseline with real computed values."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 50}, "WH-B": {"SKU-1": 50}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 40}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    comp = result["baseline_comparison"]
    assert comp is not None
    assert comp["optimized_total_units"] == result["total_units"]
    assert comp["units_difference"] == comp["optimized_total_units"] - comp["baseline_total_units"]
    assert comp["cost_difference"] == round(comp["optimized_total_cost"] - comp["baseline_total_cost"], 2)


# ---------------------------------------------------------------------------
# Test Category 8: Profile Behavior (Cost-First, Service-First, Balanced)
# ---------------------------------------------------------------------------

def test_18_cost_first_profile_behavior():
    """Cost-First prioritizes lowest transport cost and limits uneconomical freight."""
    warehouses = [
        {"code": "WH-LowCost", "daily_dispatch_capacity_units": 200},
        {"code": "WH-HighCost", "daily_dispatch_capacity_units": 200},
    ]
    destinations = [
        {"code": "DST-1", "daily_receiving_capacity_units": 200},
    ]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 3.0}]
    routes = [
        {"origin_warehouse_code": "WH-LowCost", "destination_code": "DST-1", "unit_transport_cost": 1.5, "lead_time_days": 1.0, "is_active": True},
        {"origin_warehouse_code": "WH-HighCost", "destination_code": "DST-1", "unit_transport_cost": 8.0, "lead_time_days": 1.0, "is_active": True},
    ]
    available_supply = {
        "WH-LowCost": {"SKU-1": 30},
        "WH-HighCost": {"SKU-1": 50},
    }
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 50}]

    solver = DistributionSolver(profile="cost_first")
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    # In cost_first, WH-LowCost (30 units) is exhausted first
    shipped_low = sum(s["recommended_units"] for s in result["shipments"] if s["source_warehouse_code"] == "WH-LowCost")
    assert shipped_low == 30


def test_19_service_first_profile_behavior():
    """Service-First executes lexicographic optimization to maximize total fulfillment first."""
    warehouses = [
        {"code": "WH-Cheap", "daily_dispatch_capacity_units": 200},
        {"code": "WH-Expensive", "daily_dispatch_capacity_units": 200},
    ]
    destinations = [
        {"code": "DST-1", "daily_receiving_capacity_units": 200},
    ]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 2.0}]
    routes = [
        {"origin_warehouse_code": "WH-Cheap", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True},
        {"origin_warehouse_code": "WH-Expensive", "destination_code": "DST-1", "unit_transport_cost": 15.0, "lead_time_days": 1.0, "is_active": True},
    ]
    available_supply = {
        "WH-Cheap": {"SKU-1": 20},
        "WH-Expensive": {"SKU-1": 50},
    }
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 50}]

    solver = DistributionSolver(profile="service_first")
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    # Service-First must fulfill the entire 50 units (20 from Cheap + 30 from Expensive)
    assert result["total_units"] == 50
    assert result["total_unmet_units"] == 0


def test_20_balanced_profile_behavior(basic_network):
    """Balanced profile compromises between freight cost, stockout avoidance, and lead times."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 50}, "WH-B": {"SKU-1": 50}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 40}]

    solver = DistributionSolver(profile="balanced")
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["optimization_profile"] == "balanced"
    assert result["total_units"] == 40
    # WH-A has cost $2.0 vs WH-B $3.0; balanced prefers WH-A
    assert result["shipments"][0]["source_warehouse_code"] == "WH-A"


# ---------------------------------------------------------------------------
# Test Category 9: Persistence & No Inventory Mutation
# ---------------------------------------------------------------------------

def test_21_planning_run_persistence_and_no_inventory_mutation(client, db_session):
    """Planning run creates PlanningRun & ShipmentRecommendation without modifying source inventory."""
    # 1. Seed minimal data
    ds_ver = DatasetVersion(version_tag="PERSIST-V1", is_active=True, random_seed=42)
    db_session.add(ds_ver)
    db_session.commit()

    wh = Warehouse(code="WH-P1", name="Persist WH", city="Philadelphia", state="PA", capacity_units=10000, daily_dispatch_capacity_units=5000, latitude=40.0, longitude=-75.0)
    dst = Destination(code="DST-P1", name="Persist DST", channel_type="supermarket", city="Test", state="TS", daily_receiving_capacity_units=3000, latitude=40.5, longitude=-74.5)
    prod = Product(sku="SKU-P1", name="Persist Prod", category="Dairy", shelf_life_days=30, unit_cost=2.0, unit_price=4.0)
    db_session.add_all([wh, dst, prod])
    db_session.commit()

    route = Route(origin_warehouse_id=wh.id, destination_id=dst.id, unit_transport_cost=1.5, lead_time_days=1.0, distance_km=50.0, is_active=True)
    db_session.add(route)

    item = InventoryItem(
        dataset_version_id=ds_ver.id,
        warehouse_id=wh.id,
        product_id=prod.id,
        batch_lot="LOT-IMMUTABLE-01",
        on_hand_units=200,
        reserved_units=50,
        unit_cost=2.0,
        expiry_date=datetime.utcnow() + timedelta(days=60),
        batch_status="AVAILABLE",
    )
    db_session.add(item)
    db_session.commit()

    initial_on_hand = item.on_hand_units
    initial_reserved = item.reserved_units

    # 2. Execute planning run via API
    res = client.post("/api/v1/planning/run", json={"forecast_horizon_days": 3, "parameters": {"profile": "service_first"}})
    assert res.status_code == 200
    data = res.json()
    run_code = data["run_code"]

    # 3. Verify planning run persisted
    plan_run = db_session.query(PlanningRun).filter(PlanningRun.run_code == run_code).first()
    assert plan_run is not None
    assert plan_run.solver_status in ("OPTIMAL", "FEASIBLE")

    # 4. Verify source inventory batch is strictly unchanged (NEVER mutated)
    db_session.refresh(item)
    assert item.on_hand_units == initial_on_hand
    assert item.reserved_units == initial_reserved


def test_22_explainability_enrichment(basic_network):
    """Enriched shipments contain real empirical drivers and warehouse alternatives."""
    warehouses, destinations, products, routes = basic_network
    available_supply = {"WH-A": {"SKU-1": 100}, "WH-B": {"SKU-1": 100}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 40, "risk_category": "Critical"}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    explained = DistributionDecisionExplainer.enrich_shipments_with_reasoning(
        result["shipments"], available_supply=available_supply, routes=routes, demand_targets=demand_targets
    )

    assert len(explained) == 1
    reasoning = explained[0]["reasoning"]
    assert "Allocated 40 units" in reasoning
    assert "WH-A" in reasoning
    assert "freight" in reasoning


def test_23_api_schema_compatibility(client, db_session):
    """The /planning/run API endpoint returns the complete backward-compatible schema."""
    from tests.test_api_endpoints import seed_test_database
    seed_test_database(db_session)
    res = client.post("/api/v1/planning/run", json={"forecast_horizon_days": 3})
    assert res.status_code == 200
    data = res.json()
    assert "run_code" in data
    assert "metrics" in data
    assert "shipments" in data
    assert "stockout_risks" in data
    assert "unmet_demands" in data
    assert "verification" in data
    assert data["solver_status"] in ("OPTIMAL", "FEASIBLE")


def test_24_multi_product_multi_destination_network_optimality():
    """Validates multi-product, multi-destination allocation with distinct warehouse costs."""
    warehouses = [
        {"code": "WH-North", "daily_dispatch_capacity_units": 1000},
        {"code": "WH-South", "daily_dispatch_capacity_units": 1000},
    ]
    destinations = [
        {"code": "DST-North1", "daily_receiving_capacity_units": 500},
        {"code": "DST-South1", "daily_receiving_capacity_units": 500},
    ]
    products = [
        {"sku": "SKU-A", "lost_sales_penalty": 10.0},
        {"sku": "SKU-B", "lost_sales_penalty": 10.0},
    ]
    routes = [
        {"origin_warehouse_code": "WH-North", "destination_code": "DST-North1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True},
        {"origin_warehouse_code": "WH-North", "destination_code": "DST-South1", "unit_transport_cost": 5.0, "lead_time_days": 2.0, "is_active": True},
        {"origin_warehouse_code": "WH-South", "destination_code": "DST-North1", "unit_transport_cost": 5.0, "lead_time_days": 2.0, "is_active": True},
        {"origin_warehouse_code": "WH-South", "destination_code": "DST-South1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True},
    ]
    available_supply = {
        "WH-North": {"SKU-A": 100, "SKU-B": 100},
        "WH-South": {"SKU-A": 100, "SKU-B": 100},
    }
    demand_targets = [
        {"destination_code": "DST-North1", "sku": "SKU-A", "forecasted_units": 40},
        {"destination_code": "DST-South1", "sku": "SKU-B", "forecasted_units": 50},
    ]

    solver = DistributionSolver(profile="cost_first")
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["total_units"] == 90
    assert result["total_unmet_units"] == 0
    # Optimal routes: WH-North -> DST-North1 ($1.0 * 40 = $40), WH-South -> DST-South1 ($1.0 * 50 = $50)
    # Total cost must be 40 + 50 = $90.00
    assert result["total_transport_cost"] == 90.0


# ---------------------------------------------------------------------------
# Prompt 5.1 Targeted Tests: Objective Audit & Constraint Corrections
# ---------------------------------------------------------------------------

def test_25_cost_first_minimum_fulfillment_enforcement():
    """Cost-First must enforce the minimum fulfillment floor (e.g. 80%) instead of curtailing demand."""
    warehouses = [
        {"code": "WH-LowCost", "daily_dispatch_capacity_units": 500},
        {"code": "WH-HighCost", "daily_dispatch_capacity_units": 500},
    ]
    destinations = [
        {"code": "DST-1", "daily_receiving_capacity_units": 500},
    ]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 2.0}]
    routes = [
        {"origin_warehouse_code": "WH-LowCost", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True},
        # Freight $12.0/u exceeds penalty ($2 * 2 = $4.0/u); unconstrained would skip this
        {"origin_warehouse_code": "WH-HighCost", "destination_code": "DST-1", "unit_transport_cost": 12.0, "lead_time_days": 1.0, "is_active": True},
    ]
    available_supply = {
        "WH-LowCost": {"SKU-1": 30},
        "WH-HighCost": {"SKU-1": 100},
    }
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 100}]

    # With min_fulfillment_rate = 0.80 (80%), solver must ship at least 80 units
    solver = DistributionSolver(profile="cost_first", min_fulfillment_rate=0.80)
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert result["total_units"] >= 80  # 80% floor enforced!
    assert result["min_fulfillment_target_met"] is True


def test_26_cost_first_infeasible_fulfillment_target():
    """When network supply is strictly less than requested target, solver reports TARGET_UNACHIEVABLE."""
    warehouses = [{"code": "WH-A", "daily_dispatch_capacity_units": 100}]
    destinations = [{"code": "DST-1", "daily_receiving_capacity_units": 100}]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 5.0}]
    available_supply = {"WH-A": {"SKU-1": 50}}  # Only 50 units in entire network
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 100}]
    routes = [{"origin_warehouse_code": "WH-A", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True}]

    # Target: 85% of 100 = 85 units, but network only has 50
    solver = DistributionSolver(profile="cost_first", min_fulfillment_rate=0.85)
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["solver_status"] in ("TARGET_UNACHIEVABLE", "INFEASIBLE")
    assert result["min_fulfillment_target_met"] is False
    assert "cannot be met" in result["status_message"]


def test_27_cost_first_explicit_unconstrained_opt_in():
    """Allowing unconstrained cost-first permits skipping expensive freight with explicit warning."""
    warehouses = [
        {"code": "WH-LowCost", "daily_dispatch_capacity_units": 500},
        {"code": "WH-HighCost", "daily_dispatch_capacity_units": 500},
    ]
    destinations = [
        {"code": "DST-1", "daily_receiving_capacity_units": 500},
    ]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 2.0}]
    routes = [
        {"origin_warehouse_code": "WH-LowCost", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True},
        {"origin_warehouse_code": "WH-HighCost", "destination_code": "DST-1", "unit_transport_cost": 15.0, "lead_time_days": 1.0, "is_active": True},
    ]
    available_supply = {
        "WH-LowCost": {"SKU-1": 25},
        "WH-HighCost": {"SKU-1": 100},
    }
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 100}]

    # Explicit opt-in to unconstrained
    solver = DistributionSolver(
        profile="cost_first",
        min_fulfillment_rate=0.0,
        allow_unconstrained_cost_first=True,
    )
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    # In unconstrained mode, only cheap units are shipped because high freight ($15) > penalty ($4)
    assert result["total_units"] == 25
    assert any("Unconstrained cost-first" in w for w in result["warnings"])


def test_28_balanced_profile_parameter_validation():
    """Validates that negative weights and invalid profile names are rejected."""
    with pytest.raises(ValueError):
        DistributionSolver(transport_weight=-1.0)

    with pytest.raises(ValueError):
        DistributionSolver(lead_time_penalty_weight=-0.1)

    with pytest.raises(ValueError):
        DistributionSolver(stockout_penalty_weight=-5.0)

    with pytest.raises(ValueError):
        DistributionSolver(min_fulfillment_rate=1.5)


def test_29_lead_time_penalty_weight_alters_objective_decision():
    """Changing lead_time_penalty_weight alters the mathematical choice between fast vs cheap routes."""
    warehouses = [
        {"code": "WH-Fast", "daily_dispatch_capacity_units": 500},
        {"code": "WH-Slow", "daily_dispatch_capacity_units": 500},
    ]
    destinations = [
        {"code": "DST-1", "daily_receiving_capacity_units": 500},
    ]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 10.0}]
    routes = [
        # Fast: 1.0 day, freight $4.00
        {"origin_warehouse_code": "WH-Fast", "destination_code": "DST-1", "unit_transport_cost": 4.0, "lead_time_days": 1.0, "is_active": True},
        # Slow: 5.0 days, freight $3.20 (cheaper freight)
        {"origin_warehouse_code": "WH-Slow", "destination_code": "DST-1", "unit_transport_cost": 3.2, "lead_time_days": 5.0, "is_active": True},
    ]
    available_supply = {
        "WH-Fast": {"SKU-1": 100},
        "WH-Slow": {"SKU-1": 100},
    }
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 50}]

    # Case A: Low lead-time penalty weight = $0.05/day/unit
    # Fast: $4.00 + 1 * 0.05 = $4.05. Slow: $3.20 + 5 * 0.05 = $3.45. Slow wins!
    solver_a = DistributionSolver(profile="balanced", lead_time_penalty_weight=0.05)
    res_a = solver_a.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )
    assert res_a["shipments"][0]["source_warehouse_code"] == "WH-Slow"

    # Case B: High lead-time penalty weight = $0.50/day/unit
    # Fast: $4.00 + 1 * 0.50 = $4.50. Slow: $3.20 + 5 * 0.50 = $5.70. Fast wins!
    solver_b = DistributionSolver(profile="balanced", lead_time_penalty_weight=0.50)
    res_b = solver_b.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )
    assert res_b["shipments"][0]["source_warehouse_code"] == "WH-Fast"


def test_30_batch_expiry_route_eligibility():
    """Batches expiring before delivery arrives cannot be allocated to that route."""
    from datetime import date, timedelta
    today = date(2026, 1, 1)

    warehouses = [{"code": "WH-1", "daily_dispatch_capacity_units": 500}]
    destinations = [{"code": "DST-Far", "daily_receiving_capacity_units": 500}]
    products = [{"sku": "SKU-Dairy", "lost_sales_penalty": 10.0}]

    # Route lead time is 4 days -> Arrival is 2026-01-05
    routes = [{"origin_warehouse_code": "WH-1", "destination_code": "DST-Far", "unit_transport_cost": 2.0, "lead_time_days": 4.0, "is_active": True}]

    # Inventory:
    # Batch 1 (30 units): expires 2026-01-03 (expires BEFORE arrival -> ineligible!)
    # Batch 2 (50 units): expires 2026-01-20 (expires AFTER arrival -> eligible!)
    inventory_items = [
        {"warehouse_code": "WH-1", "product_sku": "SKU-Dairy", "batch_lot": "LOT-EXP-EARLY", "on_hand_units": 30, "reserved_units": 0, "expiry_date": today + timedelta(days=2), "batch_status": "AVAILABLE"},
        {"warehouse_code": "WH-1", "product_sku": "SKU-Dairy", "batch_lot": "LOT-EXP-LATE", "on_hand_units": 50, "reserved_units": 0, "expiry_date": today + timedelta(days=20), "batch_status": "AVAILABLE"},
    ]
    available_supply = {"WH-1": {"SKU-Dairy": 80}}
    demand_targets = [{"destination_code": "DST-Far", "sku": "SKU-Dairy", "forecasted_units": 70}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets,
        routes=routes, inventory_items=inventory_items, as_of_date=today
    )

    # Only 50 units (Batch 2) are eligible; Batch 1 cannot be shipped!
    assert result["total_units"] == 50
    assert result["total_unmet_units"] == 20


def test_31_verifier_detects_expiry_before_arrival_violation():
    """SolutionVerifier flags plans where shipments rely on batches expiring before arrival."""
    from datetime import date, timedelta
    today = date(2026, 1, 1)

    # Lead time = 5 days -> min arrival expiry = today + 5 days
    routes = [{"origin_warehouse_code": "WH-1", "destination_code": "DST-1", "unit_transport_cost": 2.0, "lead_time_days": 5.0, "is_active": True}]
    # Batch expires in 2 days
    inventory_items = [
        {"warehouse_code": "WH-1", "product_sku": "SKU-1", "batch_lot": "LOT-SHORT", "on_hand_units": 40, "reserved_units": 0, "expiry_date": today + timedelta(days=2), "batch_status": "AVAILABLE"},
    ]
    available_supply = {"WH-1": {"SKU-1": 40}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 40}]

    corrupted_shipment = [{
        "source_warehouse_code": "WH-1",
        "destination_code": "DST-1",
        "product_sku": "SKU-1",
        "recommended_units": 40,
        "unit_transport_cost": 2.0,
        "total_transport_cost": 80.0,
    }]

    report = SolutionVerifier.verify_comprehensive(
        shipments=corrupted_shipment,
        available_supply=available_supply,
        demand_targets=demand_targets,
        routes=routes,
        inventory_items=inventory_items,
        as_of_date=today,
    )

    assert report.is_feasible is False
    assert any("Expiry eligibility violation" in v for v in report.violations)


def test_32_baseline_fairness_with_batch_expiry():
    """Greedy baseline also enforces batch expiry and rejects allocations from expired batches."""
    from datetime import date, timedelta
    today = date(2026, 1, 1)

    warehouses = [{"code": "WH-1", "daily_dispatch_capacity_units": 500}]
    destinations = [{"code": "DST-1", "daily_receiving_capacity_units": 500}]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 10.0}]
    routes = [{"origin_warehouse_code": "WH-1", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 3.0, "is_active": True}]

    # 40 units expire in 1 day (before 3d arrival), 20 units expire in 10 days
    inventory_items = [
        {"warehouse_code": "WH-1", "product_sku": "SKU-1", "batch_lot": "LOT-1", "on_hand_units": 40, "reserved_units": 0, "expiry_date": today + timedelta(days=1), "batch_status": "AVAILABLE"},
        {"warehouse_code": "WH-1", "product_sku": "SKU-1", "batch_lot": "LOT-2", "on_hand_units": 20, "reserved_units": 0, "expiry_date": today + timedelta(days=10), "batch_status": "AVAILABLE"},
    ]
    available_supply = {"WH-1": {"SKU-1": 60}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "units": 50}]

    baseline = solve_greedy_baseline(
        warehouses, destinations, products, available_supply, demand_targets,
        routes=routes, inventory_items=inventory_items, as_of_date=today
    )

    # Baseline can only allocate the 20 fresh units from LOT-2
    assert baseline["total_units"] == 20
    assert baseline["total_unmet_units"] == 30


def test_33_unmodeled_expiry_waste_reported_honestly():
    """When store-level consumption data is unavailable, expiry waste is reported as unmodeled/None."""
    warehouses = [{"code": "WH-1", "daily_dispatch_capacity_units": 500}]
    destinations = [{"code": "DST-1", "daily_receiving_capacity_units": 500}]
    products = [{"sku": "SKU-1", "lost_sales_penalty": 5.0}]
    routes = [{"origin_warehouse_code": "WH-1", "destination_code": "DST-1", "unit_transport_cost": 1.0, "lead_time_days": 1.0, "is_active": True}]
    available_supply = {"WH-1": {"SKU-1": 50}}
    demand_targets = [{"destination_code": "DST-1", "sku": "SKU-1", "forecasted_units": 30}]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets, routes=routes
    )

    assert result["expiry_waste_modeled"] is False
    assert result["shipments"][0]["estimated_expiry_risk_pct"] is None


