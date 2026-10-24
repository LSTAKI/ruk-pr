"""Tests for API endpoints, pagination, and response schemas."""

from datetime import datetime, timedelta
from app.db.models import (
    Warehouse,
    Destination,
    Product,
    InventoryItem,
    Route,
    DailyDemandHistory,
    DatasetVersion,
    PlanningRun,
)

def seed_test_database(db):
    ds = DatasetVersion(version_tag="v1.0-test", description="Test Version", random_seed=42)
    wh = Warehouse(
        code="WH-01", name="Central DC", city="Chicago", state="IL", capacity_units=50000, daily_dispatch_capacity_units=15000, latitude=41.87, longitude=-87.62
    )
    dst = Destination(
        code="DST-01", name="Metro 1", channel_type="supermarket", city="Evanston", state="IL", daily_receiving_capacity_units=3000, latitude=42.04, longitude=-87.68
    )
    prod = Product(
        sku="SKU-001", name="Milk", category="Dairy", unit_of_measure="L", shelf_life_days=14, unit_cost=1.2, unit_price=1.8
    )
    db.add_all([ds, wh, dst, prod])
    db.commit()

    route = Route(
        origin_warehouse_id=wh.id,
        destination_id=dst.id,
        unit_transport_cost=0.55,
        lead_time_days=1.0,
        distance_km=25.0,
        is_active=True,
    )
    item = InventoryItem(
        dataset_version_id=ds.id,
        warehouse_id=wh.id,
        product_id=prod.id,
        batch_lot="LOT-001",
        on_hand_units=500,
        reserved_units=50,
        unit_cost=1.2,
        expiry_date=datetime.utcnow() + timedelta(days=20),
        batch_status="AVAILABLE",
    )
    hist = DailyDemandHistory(
        destination_id=dst.id,
        product_id=prod.id,
        demand_date=datetime(2026, 10, 1),
        quantity_demanded=30,
        quantity_sold=30,
        is_simulated=True,
    )
    db.add_all([route, item, hist])
    db.commit()
    return ds, wh, dst, prod

def test_inventory_overview_accounting(client, db_session):
    seed_test_database(db_session)
    response = client.get("/api/v1/inventory/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["total_warehouses"] == 1
    assert data["total_products"] == 1
    assert data["total_units_on_hand"] == 500
    assert data["total_units_reserved"] == 50
    assert data["total_units_available"] == 450
    assert data["total_units_usable"] == 450

def test_list_inventory_batches_pagination(client, db_session):
    seed_test_database(db_session)
    response = client.get("/api/v1/inventory/batches?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["batches"]) == 1
    assert data["batches"][0]["batch_lot"] == "LOT-001"
    assert data["batches"][0]["usable_units"] == 450

def test_routes_endpoint_and_404(client, db_session):
    seed_test_database(db_session)
    # List routes
    res = client.get("/api/v1/routes?is_active=true")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["routes"][0]["origin_warehouse_code"] == "WH-01"

    # Get invalid route ID -> 404
    err_res = client.get("/api/v1/routes/9999")
    assert err_res.status_code == 404
    assert "not found" in err_res.json()["detail"].lower()

def test_demand_history_endpoint(client, db_session):
    seed_test_database(db_session)
    res = client.get("/api/v1/demand/history")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["records"][0]["quantity_demanded"] == 30
    assert data["records"][0]["destination_code"] == "DST-01"

def test_planning_run_and_history_endpoint(client, db_session):
    ds, wh, dst, prod = seed_test_database(db_session)
    # Execute planning run
    run_res = client.post("/api/v1/planning/run", json={"forecast_horizon_days": 3})
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["solver_status"] in ("OPTIMAL", "FEASIBLE")
    run_code = run_data["run_code"]

    # Retrieve history
    history_res = client.get("/api/v1/planning/runs")
    assert history_res.status_code == 200
    history_data = history_res.json()
    assert history_data["total"] >= 1
    assert any(r["run_code"] == run_code for r in history_data["runs"])

    # Retrieve specific run
    single_res = client.get(f"/api/v1/planning/runs/{run_code}")
    assert single_res.status_code == 200
    assert single_res.json()["run_code"] == run_code
