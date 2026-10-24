"""Tests for database models, relationships, and integrity constraints."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from app.db.models import (
    Warehouse,
    Destination,
    Product,
    InventoryItem,
    Route,
    DailyDemandHistory,
    DatasetVersion,
)

def test_warehouse_destination_product_creation(db_session):
    wh = Warehouse(
        code="WH-TEST",
        name="Test Hub",
        city="Chicago",
        state="IL",
        capacity_units=50000,
        daily_dispatch_capacity_units=15000,
        latitude=41.8781,
        longitude=-87.6298,
    )
    dst = Destination(
        code="DST-TEST",
        name="Test Store",
        channel_type="supermarket",
        city="Evanston",
        state="IL",
        daily_receiving_capacity_units=3000,
        latitude=42.0451,
        longitude=-87.6877,
    )
    prod = Product(
        sku="SKU-TEST",
        name="Test Milk",
        category="Dairy",
        unit_of_measure="L",
        shelf_life_days=14,
        unit_cost=1.20,
        unit_price=1.80,
        holding_cost_per_day=0.04,
        lost_sales_penalty=3.50,
        storage_temp_c=4.0,
        weight_kg=1.0,
    )
    db_session.add_all([wh, dst, prod])
    db_session.commit()

    assert wh.id is not None
    assert dst.id is not None
    assert prod.id is not None

def test_inventory_item_constraints(db_session):
    ds = DatasetVersion(version_tag="v-test", description="Test Version", random_seed=42)
    wh = Warehouse(code="WH-C1", name="H1", city="C", state="S", capacity_units=1000, latitude=0, longitude=0)
    prod = Product(sku="SKU-C1", name="P1", category="C", unit_of_measure="u", shelf_life_days=10, unit_cost=1, unit_price=2)
    db_session.add_all([ds, wh, prod])
    db_session.commit()

    # Valid item
    item = InventoryItem(
        dataset_version_id=ds.id,
        warehouse_id=wh.id,
        product_id=prod.id,
        batch_lot="LOT-001",
        on_hand_units=500,
        reserved_units=100,
        unit_cost=1.0,
        expiry_date=datetime.utcnow() + timedelta(days=20),
        batch_status="AVAILABLE",
    )
    db_session.add(item)
    db_session.commit()
    assert item.id is not None

    # Duplicate lot for same warehouse, product, dataset_version must raise IntegrityError
    dup_item = InventoryItem(
        dataset_version_id=ds.id,
        warehouse_id=wh.id,
        product_id=prod.id,
        batch_lot="LOT-001",
        on_hand_units=200,
        reserved_units=0,
        unit_cost=1.0,
        expiry_date=datetime.utcnow() + timedelta(days=20),
    )
    db_session.add(dup_item)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_route_relationships_and_uniqueness(db_session):
    wh = Warehouse(code="WH-R1", name="H1", city="C", state="S", capacity_units=1000, latitude=40.0, longitude=-74.0)
    dst = Destination(code="DST-R1", name="D1", channel_type="supermarket", city="C", state="S", latitude=41.0, longitude=-73.0)
    db_session.add_all([wh, dst])
    db_session.commit()

    route = Route(
        origin_warehouse_id=wh.id,
        destination_id=dst.id,
        unit_transport_cost=1.25,
        lead_time_days=1.5,
        distance_km=145.0,
        is_active=True,
    )
    db_session.add(route)
    db_session.commit()
    assert route.id is not None
    assert route.origin_warehouse.code == "WH-R1"
    assert route.destination.code == "DST-R1"

    # Duplicate route for same origin-destination pair must violate unique constraint
    dup_route = Route(
        origin_warehouse_id=wh.id,
        destination_id=dst.id,
        unit_transport_cost=2.00,
        lead_time_days=2.0,
        distance_km=145.0,
    )
    db_session.add(dup_route)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_daily_demand_history_relationship(db_session):
    dst = Destination(code="DST-DH1", name="D1", channel_type="convenience", city="C", state="S", latitude=0, longitude=0)
    prod = Product(sku="SKU-DH1", name="P1", category="C", unit_of_measure="u", shelf_life_days=10, unit_cost=1, unit_price=2)
    db_session.add_all([dst, prod])
    db_session.commit()

    demand_date = datetime(2026, 10, 1, 0, 0, 0)
    rec = DailyDemandHistory(
        destination_id=dst.id,
        product_id=prod.id,
        demand_date=demand_date,
        quantity_demanded=55,
        quantity_sold=50,
        is_simulated=True,
    )
    db_session.add(rec)
    db_session.commit()
    assert rec.id is not None
    assert rec.destination.code == "DST-DH1"
    assert rec.product.sku == "SKU-DH1"
