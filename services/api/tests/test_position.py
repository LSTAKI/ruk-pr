"""Tests for inventory positioning and stockout alerts."""

from app.engine.position.inventory_position import InventoryPositionAnalyzer

def test_calculate_warehouse_available_stock():
    inventory = [
        {"warehouse_code": "WH-01", "product_sku": "SKU-001", "on_hand_units": 500, "reserved_units": 100},
        {"warehouse_code": "WH-01", "product_sku": "SKU-001", "on_hand_units": 300, "reserved_units": 50},
        {"warehouse_code": "WH-02", "product_sku": "SKU-001", "on_hand_units": 200, "reserved_units": 0},
    ]
    stock_map = InventoryPositionAnalyzer.calculate_warehouse_available_stock(inventory)
    # WH-01: (500-100) + (300-50) = 400 + 250 = 650
    assert stock_map["WH-01"]["SKU-001"] == 650
    assert stock_map["WH-02"]["SKU-001"] == 200

def test_identify_stockout_risks():
    demands = [
        {"destination_code": "DST-01", "destination_name": "Store 1", "sku": "SKU-001", "daily_mean_demand": 20.0},
    ]
    # Current stock 20 units -> 1.0 day of supply -> HIGH risk
    current_stock = {"DST-01": {"SKU-001": 20}}
    alerts = InventoryPositionAnalyzer.identify_stockout_risks(
        demands, destination_current_stock=current_stock, critical_days_threshold=3.0
    )
    assert len(alerts) == 1
    assert alerts[0]["risk_level"] == "HIGH"
    assert alerts[0]["current_inventory_days"] == 1.0
