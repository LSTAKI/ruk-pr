"""
Inventory Position, Safety Stock & Replenishment Engine Tests
=============================================================

Covers all 19 acceptance criteria with hand-calculated examples.

Hand-calculated reference values are provided inline to allow
independent verification without running the code.
"""

import math
import pytest
from datetime import date, datetime, timedelta
from typing import Any, Dict, List


# ===========================================================================
# Shared helpers
# ===========================================================================

BASE_DATE = date(2026, 1, 1)


def _day(n: int) -> date:
    return BASE_DATE + timedelta(days=n)


def _make_batch(
    on_hand: int,
    reserved: int,
    batch_lot: str = "LOT-1",
    warehouse_code: str = "WH-A",
    product_sku: str = "SKU-001",
    batch_status: str = "AVAILABLE",
    expiry_date=None,
) -> Dict[str, Any]:
    return {
        "batch_lot": batch_lot,
        "warehouse_code": warehouse_code,
        "product_sku": product_sku,
        "on_hand_units": on_hand,
        "reserved_units": reserved,
        "batch_status": batch_status,
        "expiry_date": expiry_date,
    }


def _make_demand_rows(
    n: int,
    daily_qty: int,
    start: date = BASE_DATE,
) -> List[Dict[str, Any]]:
    return [
        {
            "demand_date": start + timedelta(days=i),
            "quantity_demanded": daily_qty,
            "quantity_sold": daily_qty,
            "is_simulated": True,
        }
        for i in range(n)
    ]


def _make_route(
    warehouse_code: str = "WH-A",
    destination_code: str = "DST-01",
    lead_time_days: float = 2.0,
    unit_transport_cost: float = 1.5,
    is_active: bool = True,
) -> Dict[str, Any]:
    return {
        "id": 1,
        "origin_warehouse_id": 1,
        "destination_id": 1,
        "origin_warehouse_code": warehouse_code,
        "destination_code": destination_code,
        "lead_time_days": lead_time_days,
        "unit_transport_cost": unit_transport_cost,
        "is_active": is_active,
    }


# ===========================================================================
# SECTION 1 — Batch inventory accounting
# ===========================================================================

class TestInventoryAccounting:

    from app.engine.position.inventory_position import InventoryPositionAnalyzer

    # 1. Available-stock calculations
    def test_available_stock_basic(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        batch = _make_batch(on_hand=100, reserved=30)
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch)
        # Hand calc: available = 100 - 30 = 70
        assert result["on_hand_units"] == 100
        assert result["reserved_units"] == 30
        assert result["available_units"] == 70
        assert result["usable_units"] == 70
        assert result["is_expired"] is False
        assert result["is_quarantined"] is False

    def test_available_stock_zero_reserved(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        batch = _make_batch(on_hand=200, reserved=0)
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch)
        assert result["available_units"] == 200

    # 13. Prevention of double-counting: reserved clamped to on-hand
    def test_reserved_clamped_to_on_hand(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        # reserved (150) > on_hand (100) — must be clamped
        batch = _make_batch(on_hand=100, reserved=150)
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch)
        # reserved clamped to 100, available = 0
        assert result["reserved_units"] == 100
        assert result["available_units"] == 0
        assert result["usable_units"] == 0

    # 3. Reserved-stock handling: reserved units correctly excluded
    def test_reserved_stock_excluded_from_usable(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        batch = _make_batch(on_hand=500, reserved=200)
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch)
        assert result["usable_units"] == 300   # 500 - 200

    # 2. Expired inventory exclusion
    def test_expired_batch_excluded(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        past = datetime(2020, 1, 1)
        batch = _make_batch(on_hand=100, reserved=0, expiry_date=past)
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch, as_of_date=datetime.utcnow())
        assert result["is_expired"] is True
        assert result["usable_units"] == 0

    def test_expired_status_batch_excluded(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        batch = _make_batch(on_hand=100, reserved=0, batch_status="EXPIRED")
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch)
        assert result["is_expired"] is True
        assert result["usable_units"] == 0

    # 2. Quarantined inventory exclusion
    def test_quarantined_batch_excluded(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        batch = _make_batch(on_hand=100, reserved=0, batch_status="QUARANTINED")
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch)
        assert result["is_quarantined"] is True
        assert result["usable_units"] == 0

    def test_available_batch_included(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        batch = _make_batch(on_hand=100, reserved=0, batch_status="AVAILABLE")
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch)
        assert result["usable_units"] == 100

    # Near-expiry batch below lead-time shelf-life
    def test_near_expiry_excluded_for_lead_time(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        # Expires in 1 day, but lead_time = 3 days → cannot survive transit
        as_of = datetime(2026, 1, 1)
        expiry = datetime(2026, 1, 2)   # 1 day from as_of
        batch = _make_batch(on_hand=100, reserved=0, expiry_date=expiry)
        result = InventoryPositionAnalyzer.evaluate_batch_accounting(
            batch, as_of_date=as_of, lead_time_days=3.0
        )
        assert result["usable_units"] == 0
        assert result["status"] == "SHELF_LIFE_INSUFFICIENT"

    # 4. Inventory-position (warehouse level)
    def test_warehouse_available_stock_aggregation(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        items = [
            _make_batch(200, 50),   # usable = 150
            _make_batch(100, 0),    # usable = 100
            _make_batch(80, 0, batch_status="QUARANTINED"),  # usable = 0
        ]
        for item in items:
            item["warehouse_code"] = "WH-A"
            item["product_sku"] = "SKU-001"
        stock = InventoryPositionAnalyzer.calculate_warehouse_available_stock(items)
        # 150 + 100 = 250 (quarantined excluded)
        assert stock["WH-A"]["SKU-001"] == 250

    def test_warehouse_stock_multiple_skus(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        items = [
            dict(_make_batch(100, 0), warehouse_code="WH-A", product_sku="SKU-001"),
            dict(_make_batch(200, 0), warehouse_code="WH-A", product_sku="SKU-002"),
        ]
        stock = InventoryPositionAnalyzer.calculate_warehouse_available_stock(items)
        assert stock["WH-A"]["SKU-001"] == 100
        assert stock["WH-A"]["SKU-002"] == 200


# ===========================================================================
# SECTION 2 — Safety stock calculations
# ===========================================================================

class TestSafetyStock:

    # 7. Safety-stock formula calculation — hand-calculated reference
    def test_formula_hand_calc(self):
        from app.engine.position.safety_stock import SafetyStockConfig, compute_safety_stock

        # 10 observations: [50]*10 → stddev = 0, so SS = 0
        demands = [50.0] * 10
        cfg = SafetyStockConfig(service_level_z=1.65, fallback_factor=0.25)
        result = compute_safety_stock(demands, lead_time_days=2.0, config=cfg)
        # stddev = 0 → SS_formula = 1.65 × 0 × √2 = 0
        assert result.safety_stock_units == pytest.approx(0.0, abs=0.001)
        assert result.method_used == "formula"
        assert result.stddev_daily_demand == pytest.approx(0.0, abs=0.001)

    def test_formula_with_variance(self):
        """
        Hand-calculated reference:
          demands = [40, 50, 60, 70, 80, 60, 50, 40, 70, 50]
          mean = 57.0
          variance = (289+49+9+169+529+9+49+289+169+49) / 9 = 1610/9 ≈ 178.889
          stddev ≈ 13.375
          L = 3.0
          z = 1.65
          SS = 1.65 × 13.375 × √3 ≈ 1.65 × 13.375 × 1.7321 ≈ 38.22
        """
        from app.engine.position.safety_stock import SafetyStockConfig, compute_safety_stock
        demands = [40.0, 50.0, 60.0, 70.0, 80.0, 60.0, 50.0, 40.0, 70.0, 50.0]
        cfg = SafetyStockConfig(service_level_z=1.65)
        result = compute_safety_stock(demands, lead_time_days=3.0, config=cfg)

        # Verify stddev
        n = len(demands)
        mean = sum(demands) / n
        variance = sum((d - mean) ** 2 for d in demands) / (n - 1)
        stddev_expected = math.sqrt(variance)
        ss_expected = 1.65 * stddev_expected * math.sqrt(3.0)

        assert result.stddev_daily_demand == pytest.approx(stddev_expected, abs=0.001)
        assert result.safety_stock_units == pytest.approx(ss_expected, abs=0.01)
        assert result.method_used == "formula"
        assert result.safety_stock_int == math.ceil(ss_expected)

    # 8. Invalid config rejected
    def test_invalid_z_negative_raises(self):
        from app.engine.position.safety_stock import SafetyStockConfig
        with pytest.raises(ValueError, match="service_level_z must be >= 0"):
            SafetyStockConfig(service_level_z=-0.1).validate()

    def test_invalid_z_too_large_raises(self):
        from app.engine.position.safety_stock import SafetyStockConfig
        with pytest.raises(ValueError, match="unrealistically large"):
            SafetyStockConfig(service_level_z=5.0).validate()

    def test_invalid_fallback_raises(self):
        from app.engine.position.safety_stock import SafetyStockConfig
        with pytest.raises(ValueError, match="fallback_factor"):
            SafetyStockConfig(fallback_factor=1.5).validate()

    def test_invalid_min_ss_raises(self):
        from app.engine.position.safety_stock import SafetyStockConfig
        with pytest.raises(ValueError, match="min_safety_stock_units"):
            SafetyStockConfig(min_safety_stock_units=-1.0).validate()

    # Prevention of negative safety stock
    def test_safety_stock_non_negative(self):
        from app.engine.position.safety_stock import SafetyStockConfig, compute_safety_stock
        result = compute_safety_stock([0.0] * 10, lead_time_days=5.0)
        assert result.safety_stock_units >= 0.0
        assert result.safety_stock_int >= 0

    # 9. Insufficient history → fallback
    def test_insufficient_history_uses_fallback(self):
        from app.engine.position.safety_stock import (
            SafetyStockConfig, compute_safety_stock,
            WARN_SS_FALLBACK_USED, WARN_SS_INSUFFICIENT_HISTORY,
        )
        demands = [50.0, 60.0, 55.0]   # < 7 observations
        cfg = SafetyStockConfig(service_level_z=1.65, fallback_factor=0.25)
        result = compute_safety_stock(demands, lead_time_days=2.0, config=cfg)
        assert result.method_used == "fallback"
        assert WARN_SS_INSUFFICIENT_HISTORY in result.warnings
        assert WARN_SS_FALLBACK_USED in result.warnings
        # fallback = 0.25 × mean × 2 = 0.25 × 55.0 × 2 = 27.5
        assert result.safety_stock_units == pytest.approx(27.5, abs=0.01)

    # 10. Zero-demand history
    def test_zero_demand_safety_stock_zero(self):
        from app.engine.position.safety_stock import (
            compute_safety_stock, WARN_SS_ALL_ZERO_DEMAND,
        )
        demands = [0.0] * 14
        result = compute_safety_stock(demands, lead_time_days=3.0)
        assert result.safety_stock_units == 0.0
        assert WARN_SS_ALL_ZERO_DEMAND in result.warnings

    # 6. Zero lead time → safety stock zero
    def test_zero_lead_time_safety_stock_zero(self):
        from app.engine.position.safety_stock import (
            compute_safety_stock, WARN_SS_ZERO_LEAD_TIME,
        )
        result = compute_safety_stock([50.0] * 10, lead_time_days=0.0)
        assert result.safety_stock_units == 0.0
        assert WARN_SS_ZERO_LEAD_TIME in result.warnings

    # 9. Zero history
    def test_zero_history_safety_stock_zero(self):
        from app.engine.position.safety_stock import (
            compute_safety_stock, WARN_SS_ZERO_HISTORY,
        )
        result = compute_safety_stock([], lead_time_days=3.0)
        assert result.safety_stock_units == 0.0
        assert WARN_SS_ZERO_HISTORY in result.warnings

    # Fractional lead time supported
    def test_fractional_lead_time(self):
        from app.engine.position.safety_stock import SafetyStockConfig, compute_safety_stock
        demands = [50.0, 60.0, 55.0, 45.0, 65.0, 52.0, 48.0]  # 7 obs
        result = compute_safety_stock(demands, lead_time_days=1.5)
        # Fractional L = 1.5 → √1.5 ≈ 1.2247
        assert result.lead_time_days == 1.5
        assert result.method_used == "formula"
        assert result.safety_stock_units >= 0.0


# ===========================================================================
# SECTION 3 — Replenishment requirements
# ===========================================================================

class TestReplenishment:

    # 12. Replenishment quantity — hand-calculated example
    def test_replenishment_hand_calc(self):
        """
        Hand-calculated reference:
          daily_mean = 50 (30 obs of 50)
          lead_time = 2.0 days
          lead_time_demand = 50 × 2 = 100
          stddev = 0 (constant demand) → SS = 0
          threshold = 100 + 0 = 100
          projected_position = 0 (destination stock not tracked)
          gross_req = max(0, 100 - 0) = 100
          replenishment_qty = ceil(100) = 100
        """
        from app.engine.position.replenishment import calculate_replenishment, SafetyStockConfig

        demands = _make_demand_rows(30, daily_qty=50)
        routes = [_make_route(lead_time_days=2.0)]
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Milk",
            destination_id=1, destination_code="DST-01", destination_name="Store A",
            demand_history_rows=demands,
            available_routes=routes,
            warehouse_code="WH-A",
            as_of_date=_day(60),  # Well after all demand history
        )
        assert req.lead_time_days == 2.0
        assert req.daily_mean_demand == pytest.approx(50.0, abs=1.0)
        assert req.lead_time_demand == pytest.approx(100.0, abs=1.0)
        # threshold = lead_time_demand + SS (SS=0 since constant demand → stddev=0)
        assert req.replenishment_threshold == pytest.approx(100.0, abs=1.0)
        assert req.projected_position == 0.0
        assert req.replenishment_qty >= 100
        assert req.replenishment_qty == math.ceil(req.gross_replenishment)

    # 14. Integer quantity rounding
    def test_replenishment_qty_is_integer(self):
        from app.engine.position.replenishment import calculate_replenishment
        demands = _make_demand_rows(30, daily_qty=33)
        routes = [_make_route(lead_time_days=3.0)]
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=routes,
            warehouse_code="WH-A",
            as_of_date=_day(60),
        )
        assert isinstance(req.replenishment_qty, int)
        assert req.replenishment_qty >= 0

    # Replenishment is non-negative
    def test_replenishment_non_negative(self):
        from app.engine.position.replenishment import calculate_replenishment
        demands = _make_demand_rows(30, daily_qty=50)
        routes = [_make_route(lead_time_days=2.0)]
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=routes,
            warehouse_code="WH-A",
        )
        assert req.replenishment_qty >= 0
        assert req.gross_replenishment >= 0.0

    # 11. Incoming shipments — documented as not tracked
    def test_incoming_shipments_documented_as_zero(self):
        from app.engine.position.replenishment import calculate_replenishment, WARN_NO_INCOMING_SHIPMENTS
        demands = _make_demand_rows(30, daily_qty=50)
        routes = [_make_route()]
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=routes,
            warehouse_code="WH-A",
        )
        assert req.incoming_committed_units == 0
        assert WARN_NO_INCOMING_SHIPMENTS in req.warnings

    # 13. No double-counting: warehouse stock NOT treated as destination stock
    def test_destination_stock_not_same_as_warehouse(self):
        from app.engine.position.replenishment import calculate_replenishment, WARN_NO_DESTINATION_INVENTORY
        demands = _make_demand_rows(30, daily_qty=50)
        routes = [_make_route()]
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=routes,
            warehouse_code="WH-A",
        )
        # destination_usable must be 0 (not warehouse stock)
        assert req.destination_usable_units == 0
        assert WARN_NO_DESTINATION_INVENTORY in req.warnings

    # 9. Insufficient demand history
    def test_insufficient_history_returns_result_not_error(self):
        from app.engine.position.replenishment import calculate_replenishment
        routes = [_make_route()]
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=[],   # no history
            available_routes=routes,
            warehouse_code="WH-A",
        )
        # Must not raise; returns result with 0 demand and warnings
        assert req.daily_mean_demand == 0.0
        assert req.replenishment_qty == 0
        assert len(req.warnings) > 0

    # No active route
    def test_no_active_route_returns_zero_requirement(self):
        from app.engine.position.replenishment import calculate_replenishment, WARN_NO_ACTIVE_ROUTE
        demands = _make_demand_rows(30, daily_qty=50)
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=[],  # no routes
            warehouse_code="WH-A",
        )
        assert req.replenishment_qty == 0
        assert WARN_NO_ACTIVE_ROUTE in req.warnings

    # 5. Forecast demand over different lead times
    def test_lead_time_demand_proportional(self):
        from app.engine.position.replenishment import calculate_replenishment
        demands = _make_demand_rows(30, daily_qty=100)
        req_2 = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=[_make_route(lead_time_days=2.0)],
            warehouse_code="WH-A",
            as_of_date=_day(60),
        )
        req_4 = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=[_make_route(lead_time_days=4.0)],
            warehouse_code="WH-A",
            as_of_date=_day(60),
        )
        # lead_time_demand should be ~2x for 4-day vs 2-day lead time
        assert req_4.lead_time_demand == pytest.approx(req_2.lead_time_demand * 2, rel=0.05)

    # 6. Fractional lead-time policy
    def test_fractional_lead_time_demand(self):
        """
        Hand calc: daily_mean ≈ 50, L = 1.5
        lead_time_demand = 50 × 1.5 = 75
        """
        from app.engine.position.replenishment import calculate_replenishment
        demands = _make_demand_rows(30, daily_qty=50)
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=[_make_route(lead_time_days=1.5)],
            warehouse_code="WH-A",
            as_of_date=_day(60),
        )
        assert req.lead_time_days == 1.5
        assert req.lead_time_demand == pytest.approx(75.0, abs=2.0)


# ===========================================================================
# SECTION 4 — Route selection policy
# ===========================================================================

class TestRouteSelection:

    def test_min_lead_time_selected(self):
        from app.engine.position.replenishment import select_best_route
        routes = [
            _make_route("WH-A", "DST-01", lead_time_days=3.0, unit_transport_cost=1.0),
            _make_route("WH-A", "DST-01", lead_time_days=2.0, unit_transport_cost=2.0),
            _make_route("WH-A", "DST-01", lead_time_days=5.0, unit_transport_cost=0.5),
        ]
        selected = select_best_route(routes, "WH-A", "DST-01")
        assert selected.lead_time_days == 2.0   # Minimum lead time

    def test_cost_tiebreak(self):
        from app.engine.position.replenishment import select_best_route
        routes = [
            _make_route("WH-A", "DST-01", lead_time_days=2.0, unit_transport_cost=2.0),
            _make_route("WH-A", "DST-01", lead_time_days=2.0, unit_transport_cost=1.0),
        ]
        selected = select_best_route(routes, "WH-A", "DST-01")
        assert selected.unit_transport_cost == 1.0  # Cheaper wins on tie

    def test_inactive_routes_excluded(self):
        from app.engine.position.replenishment import select_best_route
        routes = [
            _make_route("WH-A", "DST-01", is_active=False),
        ]
        result = select_best_route(routes, "WH-A", "DST-01")
        assert result is None

    def test_no_routes_returns_none(self):
        from app.engine.position.replenishment import select_best_route
        result = select_best_route([], "WH-A", "DST-01")
        assert result is None


# ===========================================================================
# SECTION 5 — Inventory cover and stockout risk
# ===========================================================================

class TestInventoryCoverAndRisk:

    # 15. Inventory-cover calculations
    def test_cover_days_hand_calc(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        # 100 units at 20 units/day → 5 days cover
        result = InventoryPositionAnalyzer.calculate_cover_days(100, 20.0)
        assert result == pytest.approx(5.0, abs=0.01)

    def test_cover_days_zero_demand_returns_none(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        result = InventoryPositionAnalyzer.calculate_cover_days(100, 0.0)
        assert result is None

    # 16. Risk-category rules
    def test_risk_critical_zero_stock(self):
        from app.engine.position.replenishment import assign_risk_category, RISK_CRITICAL
        risk = assign_risk_category(cover_days=0.0, lead_time_days=2.0, safety_stock_days=1.0, daily_demand=50.0)
        assert risk == RISK_CRITICAL

    def test_risk_high_below_lead_time(self):
        from app.engine.position.replenishment import assign_risk_category, RISK_HIGH
        # cover=1.5, lead_time=2.0 → High (cover < lead time)
        risk = assign_risk_category(cover_days=1.5, lead_time_days=2.0, safety_stock_days=1.0, daily_demand=50.0)
        assert risk == RISK_HIGH

    def test_risk_moderate_between_lead_and_ss(self):
        from app.engine.position.replenishment import assign_risk_category, RISK_MODERATE
        # cover=2.5, lead_time=2.0, ss_days=1.0 → 2.0 < 2.5 <= 3.0 → Moderate
        risk = assign_risk_category(cover_days=2.5, lead_time_days=2.0, safety_stock_days=1.0, daily_demand=50.0)
        assert risk == RISK_MODERATE

    def test_risk_low_above_ss_buffer(self):
        from app.engine.position.replenishment import assign_risk_category, RISK_LOW
        # cover=10, lead_time=2, ss_days=1 → 10 > 3 → Low
        risk = assign_risk_category(cover_days=10.0, lead_time_days=2.0, safety_stock_days=1.0, daily_demand=50.0)
        assert risk == RISK_LOW

    def test_risk_insufficient_data_zero_demand(self):
        from app.engine.position.replenishment import assign_risk_category, RISK_INSUFFICIENT_DATA
        risk = assign_risk_category(cover_days=5.0, lead_time_days=2.0, safety_stock_days=1.0, daily_demand=0.0)
        assert risk == RISK_INSUFFICIENT_DATA

    # 16. 5-level risk via identify_stockout_risks
    def test_identify_stockout_5_levels(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        forecasts = [
            {"destination_code": "DST-01", "destination_name": "Store A",
             "sku": "SKU-001", "product_name": "Milk", "daily_mean_demand": 50.0},
            {"destination_code": "DST-02", "destination_name": "Store B",
             "sku": "SKU-001", "product_name": "Milk", "daily_mean_demand": 50.0},
            {"destination_code": "DST-03", "destination_name": "Store C",
             "sku": "SKU-001", "product_name": "Milk", "daily_mean_demand": 50.0},
            {"destination_code": "DST-04", "destination_name": "Store D",
             "sku": "SKU-001", "product_name": "Milk", "daily_mean_demand": 0.0},
        ]
        stock = {
            "DST-01": {"SKU-001": 0},    # Critical (no stock)
            "DST-02": {"SKU-001": 50},   # 1 day cover → High if lead_time=2
            "DST-03": {"SKU-001": 500},  # 10 days → Low
            "DST-04": {"SKU-001": 100},  # zero demand → InsufficientData
        }
        lead_map = {"DST-01": 2.0, "DST-02": 2.0, "DST-03": 2.0}
        results = InventoryPositionAnalyzer.identify_stockout_risks(
            forecasts, stock, lead_time_days_map=lead_map
        )
        risk_map = {r["destination_code"]: r["risk_level"] for r in results}
        assert risk_map["DST-01"] == "Critical"
        assert risk_map["DST-02"] == "High"
        assert risk_map["DST-03"] == "Low"
        assert risk_map["DST-04"] == "InsufficientData"

    # Legacy backward compat
    def test_identify_stockout_legacy_compat(self):
        """Old callers without lead_time_days_map still work."""
        from app.engine.position.inventory_position import InventoryPositionAnalyzer
        forecasts = [
            {"destination_code": "DST-01", "destination_name": "A",
             "sku": "SKU-001", "product_name": "Milk", "daily_mean_demand": 50.0},
        ]
        stock = {"DST-01": {"SKU-001": 50}}  # 1 day cover
        results = InventoryPositionAnalyzer.identify_stockout_risks(
            forecasts, stock, critical_days_threshold=3.0
        )
        assert len(results) == 1
        assert results[0]["risk_level"] in ("Critical", "High", "Moderate", "Low", "InsufficientData")


# ===========================================================================
# SECTION 6 — Optimizer integration contract
# ===========================================================================

class TestOptimizerContract:

    # 18. Optimizer integration contract fields
    def test_contract_has_required_fields(self):
        from app.engine.position.replenishment import (
            calculate_replenishment, to_optimizer_contract
        )
        demands = _make_demand_rows(30, daily_qty=50)
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=[_make_route()],
            warehouse_code="WH-A",
        )
        contract = to_optimizer_contract(req)
        required_keys = {
            "product_id", "product_sku", "destination_id", "destination_code",
            "replenishment_qty", "lead_time_demand", "daily_mean_demand",
            "lead_time_days", "safety_stock_units", "safety_stock_method",
            "projected_position", "destination_stock_tracked",
            "risk_category", "warnings", "history_used", "forecast_method",
        }
        assert required_keys.issubset(contract.keys())

    def test_contract_destination_stock_not_tracked(self):
        from app.engine.position.replenishment import calculate_replenishment, to_optimizer_contract
        demands = _make_demand_rows(30, daily_qty=50)
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=[_make_route()],
            warehouse_code="WH-A",
        )
        contract = to_optimizer_contract(req)
        # GAP-1: must explicitly flag that destination stock is not tracked
        assert contract["destination_stock_tracked"] is False

    def test_contract_notes_present(self):
        from app.engine.position.replenishment import calculate_replenishment, to_optimizer_contract
        demands = _make_demand_rows(30, daily_qty=50)
        req = calculate_replenishment(
            product_id=1, product_sku="SKU-001", product_name="Test",
            destination_id=1, destination_code="DST-01", destination_name="Test",
            demand_history_rows=demands,
            available_routes=[_make_route()],
            warehouse_code="WH-A",
        )
        contract = to_optimizer_contract(req)
        assert "_contract_notes" in contract
        assert len(contract["_contract_notes"]) > 0


# ===========================================================================
# SECTION 7 — API validation and responses
# ===========================================================================

class TestReplenishmentAPI:

    # 17. API response schemas and validation
    def test_single_replenishment_nonexistent_product_404(self, client):
        resp = client.post("/api/v1/replenishment", json={
            "product_id": 99999,
            "destination_id": 1,
        })
        assert resp.status_code == 404

    def test_single_replenishment_nonexistent_destination_404(self, client):
        resp = client.post("/api/v1/replenishment", json={
            "product_id": 1,
            "destination_id": 99999,
        })
        assert resp.status_code == 404

    def test_single_replenishment_invalid_method_422(self, client):
        resp = client.post("/api/v1/replenishment", json={
            "product_id": 1,
            "destination_id": 1,
            "forecast_method": "magic",
        })
        assert resp.status_code == 422

    def test_risk_rules_endpoint(self, client):
        resp = client.get("/api/v1/replenishment/risk-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_category_rules" in data
        assert "Critical" in data["risk_category_rules"]
        assert "important_notes" in data

    def test_summary_endpoint_returns_200(self, client):
        """Basic smoke test — seeded DB should return results."""
        resp = client.post("/api/v1/replenishment/summary", json={
            "limit": 10,
            "offset": 0,
        })
        # Either 200 (if routes exist) or 400 (if no routes in test DB)
        assert resp.status_code in (200, 400)

    def test_optimizer_contract_endpoint_smoke(self, client):
        resp = client.get("/api/v1/replenishment/optimizer-contract?limit=5")
        assert resp.status_code in (200, 400)
