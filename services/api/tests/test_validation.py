"""Tests for input and constraint validation."""

from datetime import datetime, timedelta
from app.engine.validation.validator import DistributionPlanValidator

def test_validate_negative_inventory_rejected():
    inventory = [{
        "warehouse_code": "WH-01",
        "product_sku": "SKU-0001",
        "batch_lot": "LOT-BAD",
        "on_hand_units": -50,
        "reserved_units": 0,
        "expiry_date": datetime.utcnow() + timedelta(days=20),
    }]
    valid, errors = DistributionPlanValidator.validate_supply_and_demand(
        warehouses=[],
        inventory_items=inventory,
        demand_targets=[],
        as_of_date=datetime.utcnow(),
    )
    assert not valid
    assert any("Negative on_hand_units" in e for e in errors)

def test_validate_reserved_exceeding_on_hand():
    inventory = [{
        "warehouse_code": "WH-01",
        "product_sku": "SKU-0001",
        "batch_lot": "LOT-ERR",
        "on_hand_units": 100,
        "reserved_units": 150,
        "expiry_date": datetime.utcnow() + timedelta(days=20),
    }]
    valid, errors = DistributionPlanValidator.validate_supply_and_demand(
        warehouses=[],
        inventory_items=inventory,
        demand_targets=[],
        as_of_date=datetime.utcnow(),
    )
    assert not valid
    assert any("exceed on-hand" in e for e in errors)
