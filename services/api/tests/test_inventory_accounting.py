"""Tests for standardized inventory accounting definitions and rules."""

from datetime import datetime, timedelta
from app.engine.position.inventory_position import InventoryPositionAnalyzer

def test_inventory_accounting_hierarchy():
    now = datetime(2026, 10, 24, 12, 0, 0)

    # 1. Normal unreserved available batch
    batch1 = {
        "batch_lot": "LOT-NORMAL",
        "warehouse_code": "WH-01",
        "product_sku": "SKU-001",
        "on_hand_units": 500,
        "reserved_units": 100,
        "expiry_date": now + timedelta(days=30),
        "batch_status": "AVAILABLE",
    }
    eval1 = InventoryPositionAnalyzer.evaluate_batch_accounting(batch1, as_of_date=now)
    assert eval1["on_hand_units"] == 500
    assert eval1["reserved_units"] == 100
    assert eval1["available_units"] == 400
    assert eval1["usable_units"] == 400
    assert eval1["status"] == "AVAILABLE"

    # 2. Expired batch must have usable_units = 0
    batch_expired = {
        "batch_lot": "LOT-EXPIRED",
        "warehouse_code": "WH-01",
        "product_sku": "SKU-001",
        "on_hand_units": 250,
        "reserved_units": 0,
        "expiry_date": now - timedelta(days=2),
        "batch_status": "AVAILABLE",
    }
    eval_exp = InventoryPositionAnalyzer.evaluate_batch_accounting(batch_expired, as_of_date=now)
    assert eval_exp["is_expired"] is True
    assert eval_exp["usable_units"] == 0
    assert eval_exp["status"] == "EXPIRED"

    # 3. Quarantined batch must have usable_units = 0
    batch_quarantine = {
        "batch_lot": "LOT-QUAR",
        "warehouse_code": "WH-01",
        "product_sku": "SKU-001",
        "on_hand_units": 300,
        "reserved_units": 50,
        "expiry_date": now + timedelta(days=40),
        "batch_status": "QUARANTINED",
    }
    eval_quar = InventoryPositionAnalyzer.evaluate_batch_accounting(batch_quarantine, as_of_date=now)
    assert eval_quar["is_quarantined"] is True
    assert eval_quar["usable_units"] == 0
    assert eval_quar["status"] == "QUARANTINED"

    # 4. Insufficient shelf life for transit lead time
    batch_near_expiry = {
        "batch_lot": "LOT-NEAR",
        "warehouse_code": "WH-01",
        "product_sku": "SKU-001",
        "on_hand_units": 150,
        "reserved_units": 0,
        "expiry_date": now + timedelta(days=1),  # 1 day shelf life remaining
        "batch_status": "AVAILABLE",
    }
    # Require 2 days transit lead time
    eval_near = InventoryPositionAnalyzer.evaluate_batch_accounting(batch_near_expiry, as_of_date=now, lead_time_days=2.0)
    assert eval_near["usable_units"] == 0
    assert eval_near["status"] == "SHELF_LIFE_INSUFFICIENT"

def test_warehouse_usable_stock_filtering():
    now = datetime(2026, 10, 24, 12, 0, 0)
    batches = [
        # Usable: 400 - 100 = 300
        {"warehouse_code": "WH-01", "product_sku": "SKU-01", "on_hand_units": 400, "reserved_units": 100, "expiry_date": now + timedelta(days=20), "batch_status": "AVAILABLE"},
        # Expired: 0
        {"warehouse_code": "WH-01", "product_sku": "SKU-01", "on_hand_units": 500, "reserved_units": 0, "expiry_date": now - timedelta(days=1), "batch_status": "EXPIRED"},
        # Quarantined: 0
        {"warehouse_code": "WH-01", "product_sku": "SKU-01", "on_hand_units": 200, "reserved_units": 0, "expiry_date": now + timedelta(days=30), "batch_status": "QUARANTINED"},
        # WH-02 Usable: 600 - 50 = 550
        {"warehouse_code": "WH-02", "product_sku": "SKU-01", "on_hand_units": 600, "reserved_units": 50, "expiry_date": now + timedelta(days=20), "batch_status": "AVAILABLE"},
    ]

    usable_stock = InventoryPositionAnalyzer.calculate_warehouse_available_stock(batches, as_of_date=now, require_usable=True)
    assert usable_stock["WH-01"]["SKU-01"] == 300
    assert usable_stock["WH-02"]["SKU-01"] == 550
