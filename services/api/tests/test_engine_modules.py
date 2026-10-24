"""Integration tests for optimization solver, verifier, and explainer modules."""

from app.engine.optimize.solver import DistributionSolver, calculate_geo_distance_km
from app.engine.verify.verifier import SolutionVerifier
from app.engine.explain.explainer import DistributionDecisionExplainer

def test_geo_distance():
    # Chicago to NYC ~ 1145 km
    dist = calculate_geo_distance_km(41.8781, -87.6298, 40.7128, -74.0060)
    assert 1100 <= dist <= 1200

def test_distribution_solver_execution():
    warehouses = [
        {"code": "WH-01", "name": "Hub 1", "latitude": 41.8781, "longitude": -87.6298},
        {"code": "WH-02", "name": "Hub 2", "latitude": 40.7128, "longitude": -74.0060},
    ]
    destinations = [
        {"code": "DST-01", "name": "Store 1", "latitude": 41.8818, "longitude": -87.6231},
    ]
    products = [
        {"sku": "SKU-001", "name": "Milk 1L"},
    ]
    available_supply = {
        "WH-01": {"SKU-001": 500},
        "WH-02": {"SKU-001": 500},
    }
    demand_targets = [
        {"destination_code": "DST-01", "sku": "SKU-001", "forecasted_units": 100},
    ]

    solver = DistributionSolver()
    result = solver.solve_distribution_plan(
        warehouses, destinations, products, available_supply, demand_targets
    )

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert result["total_units"] == 100
    assert len(result["shipments"]) == 1

    # WH-01 is in Chicago, right next to DST-01. The solver must choose WH-01 over WH-02
    shipment = result["shipments"][0]
    assert shipment["source_warehouse_code"] == "WH-01"
    assert shipment["recommended_units"] == 100

    # Test verifier
    is_feasible, violations = SolutionVerifier.verify_plan_feasibility(
        result["shipments"], available_supply, demand_targets
    )
    assert is_feasible
    assert len(violations) == 0

    # Test explainer
    explained = DistributionDecisionExplainer.enrich_shipments_with_reasoning(result["shipments"])
    assert len(explained) == 1
    assert "WH-01" in explained[0]["reasoning"]
