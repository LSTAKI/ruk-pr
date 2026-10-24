"""Tests for routes, throughput capacities, and historical demand coverage."""

from datetime import datetime, timedelta
from app.engine.simulator.fmcg_generator import DeterministicFMCGSimulator
from app.engine.validation.validator import DistributionPlanValidator

def test_demand_history_coverage_and_structure():
    sim = DeterministicFMCGSimulator(seed=42)
    data = sim.generate_dataset(num_warehouses=4, num_destinations=10, demand_history_days=120)

    history = data["demand_history"]
    # 10 destinations x 16 products x 120 days = 19,200 records
    assert len(history) == 10 * 16 * 120

    dates = set(h["demand_date"] for h in history)
    assert len(dates) == 120

    for rec in history[:50]:
        assert rec["quantity_demanded"] >= 0
        assert rec["quantity_sold"] >= 0
        assert rec["quantity_sold"] <= rec["quantity_demanded"]
        assert rec["is_simulated"] is True
        assert "destination_code" in rec
        assert "product_sku" in rec

def test_routes_generation_and_edge_cases():
    sim = DeterministicFMCGSimulator(seed=42)
    data = sim.generate_dataset(num_warehouses=4, num_destinations=50)

    routes = data["routes"]
    assert len(routes) == 4 * 50  # 200 routes

    # Check for inactive routes (Edge case 6: remote pair ineligibility)
    inactive_routes = [r for r in routes if not r["is_active"]]
    assert len(inactive_routes) > 0

    for r in routes:
        assert r["distance_km"] > 0
        assert r["unit_transport_cost"] >= 0.45
        assert r["lead_time_days"] >= 1.0

def test_throughput_capacity_validation():
    shipments = [
        {"source_warehouse_code": "WH-01", "destination_code": "DST-001", "recommended_units": 6000},
        {"source_warehouse_code": "WH-01", "destination_code": "DST-002", "recommended_units": 5000},
    ]
    # WH-01 total dispatched = 11,000. Limit = 10,000 -> exceeds
    # DST-001 received = 6,000. Limit = 5,000 -> exceeds
    wh_limits = {"WH-01": 10000}
    dst_limits = {"DST-001": 5000, "DST-002": 10000}

    is_valid, errors = DistributionPlanValidator.validate_throughput_capacities(
        shipments, wh_limits, dst_limits
    )
    assert not is_valid
    assert any("WH-01 exceeds daily dispatch capacity" in e for e in errors)
    assert any("DST-001 exceeds daily receiving capacity" in e for e in errors)
