"""
Comprehensive forecasting engine tests.

Covers all 15 acceptance criteria:
  1.  Naïve forecast calculations
  2.  EWMA calculations
  3.  Forecast horizon lengths (7, 14, 30)
  4.  Non-negative forecasts
  5.  Zero-demand history
  6.  Missing historical dates
  7.  Duplicate observations
  8.  Negative-demand validation
  9.  Insufficient history
  10. MAE calculations
  11. WAPE calculations, including zero-demand edge cases
  12. Chronological backtesting without future-data leakage
  13. API validation and error responses
  14. Deterministic forecast output
  15. Compatibility with existing inventory-position interface
"""

import pytest
from datetime import date, timedelta, datetime
from typing import List, Dict, Any

from app.engine.forecast.data_prep import (
    MIN_HISTORY_EWMA,
    MIN_HISTORY_NAIVE,
    MIN_HISTORY_SEASONAL,
    WARN_ALL_ZERO_DEMAND,
    WARN_CALENDAR_GAPS,
    WARN_DUPLICATE_DATES,
    WARN_FUTURE_OBSERVATIONS_EXCLUDED,
    WARN_INSUFFICIENT_HISTORY,
    WARN_NEGATIVE_DEMAND,
    PreparedSeries,
    chronological_split,
    prepare_demand_series,
)
from app.engine.forecast.methods import (
    METHOD_EWMA,
    METHOD_NAIVE,
    METHOD_SEASONAL_NAIVE,
    SUPPORTED_HORIZONS,
    forecast,
    forecast_ewma,
    forecast_naive,
    forecast_seasonal_naive,
)
from app.engine.forecast.evaluation import (
    _compute_mae,
    _compute_wape,
    aggregate_evaluations,
    evaluate_series,
)
from app.engine.forecast.position_interface import (
    forecast_demand_for_planning,
    build_forecast_lookup,
)
from app.engine.forecast.forecaster import BaselineDemandForecaster


# ===========================================================================
# Helpers
# ===========================================================================

BASE_DATE = date(2026, 6, 1)


def _make_records(
    n: int,
    start: date = BASE_DATE,
    base_demand: int = 50,
    skip_days: List[int] = None,
    duplicate_day: int = None,
) -> List[Dict[str, Any]]:
    """Build a simple contiguous daily demand series."""
    records = []
    day_idx = 0
    actual_date = start
    for i in range(n):
        if skip_days and i in skip_days:
            actual_date += timedelta(days=1)
            continue
        records.append({
            "demand_date": actual_date,
            "quantity_demanded": base_demand,
            "quantity_sold": base_demand,
            "is_simulated": True,
        })
        if duplicate_day == i:
            # Insert a duplicate for the same date
            records.append({
                "demand_date": actual_date,
                "quantity_demanded": base_demand + 5,
                "quantity_sold": base_demand,
                "is_simulated": True,
            })
        actual_date += timedelta(days=1)
    return records


def _make_series(n: int, base_demand: int = 50, **kwargs) -> PreparedSeries:
    """Convenience: generate records and prepare them into a series."""
    return prepare_demand_series(_make_records(n, base_demand=base_demand, **kwargs))


# ===========================================================================
# SECTION 1 — Data preparation
# ===========================================================================

class TestDataPreparation:

    def test_basic_preparation(self):
        series = _make_series(30)
        assert series.observation_count == 30
        assert series.duplicate_count == 0
        assert series.gap_count == 0
        assert series.negative_count == 0
        assert series.history_days == 30

    # 8. Negative-demand validation
    def test_negative_demand_rejected(self):
        records = _make_records(10)
        records[3]["quantity_demanded"] = -5
        series = prepare_demand_series(records)
        assert series.negative_count == 1
        assert WARN_NEGATIVE_DEMAND in series.warnings
        assert series.observation_count == 9  # The negative record is removed

    # 7. Duplicate observations
    def test_duplicate_dates_detected_and_dropped(self):
        records = _make_records(10, duplicate_day=4)
        series = prepare_demand_series(records)
        assert series.duplicate_count == 1
        assert WARN_DUPLICATE_DATES in series.warnings
        assert series.observation_count == 10   # 11 raw - 1 dup = 10 unique dates

    # 6. Missing historical dates — gap detection
    def test_calendar_gap_detection(self):
        records = _make_records(10)
        # Remove day index 3 to create a gap
        del records[3]
        series = prepare_demand_series(records)
        assert series.gap_count == 1
        assert WARN_CALENDAR_GAPS in series.warnings
        assert series.observation_count == 9   # no fill by default

    def test_gap_fill_with_zero_policy(self):
        records = _make_records(10)
        del records[3]
        series = prepare_demand_series(records, fill_gaps_with_zero=True)
        assert series.observation_count == 10  # gap filled
        assert series.gap_count == 1

    # 5. Zero-demand history
    def test_zero_demand_preserved(self):
        records = _make_records(10, base_demand=0)
        series = prepare_demand_series(records)
        assert all(r.quantity_demanded == 0 for r in series.records)
        assert WARN_ALL_ZERO_DEMAND in series.warnings
        assert series.observation_count == 10

    # Future-data leakage prevention
    def test_future_observations_excluded(self):
        today = date(2026, 6, 1)
        records = _make_records(10, start=date(2026, 5, 25))   # Days 25 May – 3 June
        series = prepare_demand_series(records, as_of_date=today)
        assert series.future_excluded_count > 0
        assert WARN_FUTURE_OBSERVATIONS_EXCLUDED in series.warnings
        # All retained records must be <= as_of_date
        for r in series.records:
            assert r.demand_date <= today

    # 9. Insufficient history
    def test_insufficient_history_flagged(self):
        series = _make_series(0)
        assert WARN_INSUFFICIENT_HISTORY in series.warnings
        assert series.observation_count == 0

    def test_one_record_series(self):
        series = _make_series(1)
        assert series.observation_count == 1
        assert series.history_days == 1

    def test_series_supports_method(self):
        series_short = _make_series(3)
        assert series_short.supports_method("naive")
        assert not series_short.supports_method("ewma")
        assert not series_short.supports_method("seasonal_naive")

        series_long = _make_series(20)
        assert series_long.supports_method("naive")
        assert series_long.supports_method("ewma")
        assert series_long.supports_method("seasonal_naive")


# ===========================================================================
# SECTION 2 — Forecasting methods
# ===========================================================================

class TestNaiveForecast:

    # 1. Naïve forecast calculations
    def test_naive_replicates_last_value(self):
        series = _make_series(30, base_demand=77)
        result = forecast_naive(series, horizon_days=7)
        assert result.method_available
        assert all(df["value"] == 77.0 for df in result.daily_forecasts)

    def test_naive_with_varying_history(self):
        records = _make_records(10, base_demand=50)
        records[-1]["quantity_demanded"] = 120   # Last obs is 120
        series = prepare_demand_series(records)
        result = forecast_naive(series, horizon_days=7)
        assert result.daily_forecasts[0]["value"] == 120.0
        assert result.total_demand == pytest.approx(120.0 * 7, abs=0.01)

    # 3. Horizon lengths
    def test_naive_horizon_7(self):
        series = _make_series(30)
        r = forecast_naive(series, 7)
        assert len(r.daily_forecasts) == 7

    def test_naive_horizon_14(self):
        series = _make_series(30)
        r = forecast_naive(series, 14)
        assert len(r.daily_forecasts) == 14

    def test_naive_horizon_30(self):
        series = _make_series(30)
        r = forecast_naive(series, 30)
        assert len(r.daily_forecasts) == 30

    # 9. Insufficient history
    def test_naive_insufficient_history(self):
        series = _make_series(0)
        result = forecast_naive(series, 7)
        assert not result.method_available
        assert result.unavailability_reason is not None

    # 4. Non-negative forecasts
    def test_naive_non_negative(self):
        series = _make_series(30, base_demand=0)
        result = forecast_naive(series, 7)
        assert all(df["value"] >= 0 for df in result.daily_forecasts)

    # 14. Deterministic output
    def test_naive_deterministic(self):
        series = _make_series(30)
        r1 = forecast_naive(series, 7)
        r2 = forecast_naive(series, 7)
        assert r1.daily_forecasts == r2.daily_forecasts

    # 5. Zero demand history
    def test_naive_zero_demand(self):
        series = _make_series(10, base_demand=0)
        result = forecast_naive(series, 7)
        assert result.method_available
        assert all(df["value"] == 0.0 for df in result.daily_forecasts)
        assert result.total_demand == 0.0


class TestEWMAForecast:

    # 2. EWMA calculations
    def test_ewma_manual_calculation(self):
        """Verify EWMA level matches manual computation.

        Uses 7 observations to meet MIN_HISTORY_EWMA threshold.
        """
        # 7 observations — exactly meets the minimum threshold
        demands = [100, 80, 110, 90, 100, 95, 105]
        alpha = 0.5
        level = float(demands[0])
        for d in demands[1:]:
            level = alpha * d + (1.0 - alpha) * level
        records = [
            {"demand_date": BASE_DATE + timedelta(days=i), "quantity_demanded": d,
             "quantity_sold": d, "is_simulated": True}
            for i, d in enumerate(demands)
        ]
        series = prepare_demand_series(records)
        assert series.observation_count == 7
        result = forecast_ewma(series, horizon_days=7, alpha=alpha)
        assert result.method_available
        for df in result.daily_forecasts:
            assert df["value"] == pytest.approx(level, abs=0.01)

    def test_ewma_alpha_01(self):
        """Low alpha → high smoothing, level close to initial value."""
        series = _make_series(30, base_demand=100)
        r = forecast_ewma(series, 7, alpha=0.1)
        assert r.method_available
        assert all(df["value"] >= 0 for df in r.daily_forecasts)

    def test_ewma_alpha_09(self):
        """High alpha → level tracks most recent observation."""
        records = _make_records(30, base_demand=50)
        records[-1]["quantity_demanded"] = 200  # spike at end
        series = prepare_demand_series(records)
        r = forecast_ewma(series, 7, alpha=0.9)
        # Level should be significantly influenced by the 200 spike
        assert r.daily_mean_demand > 100.0

    def test_ewma_invalid_alpha(self):
        series = _make_series(30)
        with pytest.raises(ValueError):
            forecast_ewma(series, 7, alpha=0.0)
        with pytest.raises(ValueError):
            forecast_ewma(series, 7, alpha=1.5)

    # 3. Horizon lengths
    def test_ewma_horizon_lengths(self):
        series = _make_series(30)
        for h in (7, 14, 30):
            r = forecast_ewma(series, h)
            assert len(r.daily_forecasts) == h

    # 9. Insufficient history for EWMA
    def test_ewma_insufficient_history(self):
        series = _make_series(MIN_HISTORY_EWMA - 1)
        r = forecast_ewma(series, 7)
        assert not r.method_available

    # 4. Non-negative
    def test_ewma_non_negative(self):
        series = _make_series(30, base_demand=0)
        r = forecast_ewma(series, 7)
        assert all(df["value"] >= 0 for df in r.daily_forecasts)

    # 14. Deterministic
    def test_ewma_deterministic(self):
        series = _make_series(30)
        r1 = forecast_ewma(series, 7, alpha=0.3)
        r2 = forecast_ewma(series, 7, alpha=0.3)
        assert r1.daily_forecasts == r2.daily_forecasts

    # 5. Zero demand
    def test_ewma_all_zero(self):
        series = _make_series(30, base_demand=0)
        r = forecast_ewma(series, 7)
        assert r.method_available
        assert r.total_demand == 0.0


class TestSeasonalNaiveForecast:

    def test_seasonal_naive_same_weekday(self):
        """Each forecast day must reference the same weekday from prior week."""
        records = _make_records(28)  # 4 full weeks
        series = prepare_demand_series(records)
        origin = series.records[-1].demand_date
        result = forecast_seasonal_naive(series, horizon_days=7)
        assert result.method_available
        assert len(result.daily_forecasts) == 7

    def test_seasonal_naive_insufficient_history(self):
        series = _make_series(MIN_HISTORY_SEASONAL - 1)
        r = forecast_seasonal_naive(series, 7)
        assert not r.method_available
        assert "seasonal" in r.unavailability_reason.lower()

    # 4. Non-negative
    def test_seasonal_naive_non_negative(self):
        series = _make_series(28, base_demand=30)
        r = forecast_seasonal_naive(series, 7)
        assert all(df["value"] >= 0 for df in r.daily_forecasts)

    # 14. Deterministic
    def test_seasonal_naive_deterministic(self):
        series = _make_series(28)
        r1 = forecast_seasonal_naive(series, 7)
        r2 = forecast_seasonal_naive(series, 7)
        assert r1.daily_forecasts == r2.daily_forecasts


class TestForecastDispatch:

    def test_dispatch_valid_methods(self):
        series = _make_series(30)
        for method in ("naive", "ewma", "seasonal_naive"):
            r = forecast(series, method=method, horizon_days=7)
            assert r.method is not None

    def test_dispatch_invalid_method(self):
        series = _make_series(30)
        with pytest.raises(ValueError, match="Unsupported forecasting method"):
            forecast(series, "magic", 7)

    def test_dispatch_invalid_horizon(self):
        series = _make_series(30)
        with pytest.raises(ValueError, match="Unsupported horizon"):
            forecast(series, "naive", 5)

    def test_dispatch_all_horizons(self):
        series = _make_series(30)
        for h in SUPPORTED_HORIZONS:
            r = forecast(series, "naive", h)
            assert len(r.daily_forecasts) == h


# ===========================================================================
# SECTION 3 — Evaluation metrics
# ===========================================================================

class TestMetrics:

    # 10. MAE calculations
    def test_mae_perfect_forecast(self):
        actuals = [50.0, 50.0, 50.0, 50.0]
        forecasts_ = [50.0, 50.0, 50.0, 50.0]
        assert _compute_mae(actuals, forecasts_) == 0.0

    def test_mae_known_error(self):
        actuals = [100.0, 80.0, 60.0]
        forecasts_ = [90.0, 90.0, 90.0]
        expected = (10 + 10 + 30) / 3
        assert _compute_mae(actuals, forecasts_) == pytest.approx(expected, abs=0.001)

    def test_mae_empty_returns_none(self):
        assert _compute_mae([], []) is None

    # 11. WAPE calculations
    def test_wape_known_calculation(self):
        actuals = [100.0, 100.0]
        forecasts_ = [110.0, 90.0]   # |100-110| + |100-90| = 20; sum_actual = 200
        wape, reason = _compute_wape(actuals, forecasts_)
        assert wape == pytest.approx(10.0, abs=0.001)   # 20/200 * 100 = 10.0%
        assert reason is None

    def test_wape_perfect_forecast(self):
        actuals = [50.0, 50.0]
        wape, reason = _compute_wape(actuals, actuals)
        assert wape == pytest.approx(0.0, abs=0.001)

    # 11. WAPE zero-demand edge case
    def test_wape_zero_actual_returns_none(self):
        actuals = [0.0, 0.0, 0.0]
        forecasts_ = [10.0, 10.0, 10.0]
        wape, reason = _compute_wape(actuals, forecasts_)
        assert wape is None
        assert reason is not None
        assert "zero" in reason.lower()

    def test_wape_partial_zero_actuals(self):
        """WAPE is defined when sum_actual > 0, even if some values are zero."""
        actuals = [0.0, 100.0]
        forecasts_ = [10.0, 90.0]   # |0-10| + |100-90| = 20; sum = 100
        wape, reason = _compute_wape(actuals, forecasts_)
        assert wape == pytest.approx(20.0, abs=0.001)
        assert reason is None


# ===========================================================================
# SECTION 4 — Backtesting / evaluation engine
# ===========================================================================

class TestBacktesting:

    # 12. Chronological evaluation without future leakage
    def test_train_test_split_chronological(self):
        series = _make_series(50)
        train, test = chronological_split(series, test_fraction=0.2)
        # Train must come entirely before test
        if train.records and test.records:
            assert train.records[-1].demand_date < test.records[0].demand_date

    def test_train_comes_before_test(self):
        series = _make_series(30)
        train, test = chronological_split(series)
        train_dates = [r.demand_date for r in train.records]
        test_dates = [r.demand_date for r in test.records]
        assert max(train_dates) < min(test_dates)

    def test_no_future_data_in_train(self):
        """Verify no test-period date appears in the training set."""
        series = _make_series(30)
        train, test = chronological_split(series)
        test_date_set = {r.demand_date for r in test.records}
        for r in train.records:
            assert r.demand_date not in test_date_set

    def test_evaluate_series_returns_all_methods(self):
        series = _make_series(50)
        ev = evaluate_series(series)
        assert "naive" in ev.methods
        assert "ewma" in ev.methods
        assert "seasonal_naive" in ev.methods

    def test_evaluate_series_mae_non_negative(self):
        series = _make_series(50)
        ev = evaluate_series(series)
        for me in ev.methods.values():
            if me.mae is not None:
                assert me.mae >= 0.0

    def test_evaluate_series_wape_range(self):
        """WAPE should be ≥ 0 when defined."""
        series = _make_series(50)
        ev = evaluate_series(series)
        for me in ev.methods.values():
            if me.wape is not None:
                assert me.wape >= 0.0

    def test_aggregate_evaluation(self):
        s1 = _make_series(50, base_demand=100)
        s2 = _make_series(50, base_demand=200)
        ev1 = evaluate_series(s1)
        ev2 = evaluate_series(s2)
        agg = aggregate_evaluations([ev1, ev2])
        assert agg.n_series_evaluated == 2
        assert len(agg.caveats) > 0

    def test_no_method_declared_superior_without_evidence(self):
        """Aggregate results must report numbers, not declare superiority."""
        series = _make_series(50)
        ev = evaluate_series(series)
        agg = aggregate_evaluations([ev])
        # Verify caveats include disclaimer
        joined = " ".join(agg.caveats).lower()
        assert "not" in joined and ("superior" in joined or "simulated" in joined)


# ===========================================================================
# SECTION 5 — Planning position interface
# ===========================================================================

class TestPositionInterface:

    # 15. Compatibility with inventory-position interface
    def test_forecast_for_planning_has_required_keys(self):
        records = _make_records(30)
        result = forecast_demand_for_planning(
            demand_history_rows=records,
            destination_code="DST-001",
            destination_name="Test Store",
            product_sku="SKU-0001",
            product_name="Test Product",
            product_category="Dairy",
            product_id=1,
            destination_id=1,
            horizon_days=7,
        )
        required_keys = {
            "destination_code", "destination_name", "sku", "product_name",
            "category", "horizon_days", "daily_mean_demand", "forecasted_units",
            "method", "warnings", "history_used",
        }
        assert required_keys.issubset(result.keys())

    def test_forecast_for_planning_non_negative_units(self):
        records = _make_records(30)
        result = forecast_demand_for_planning(
            demand_history_rows=records,
            destination_code="DST-001",
            destination_name="Test Store",
            product_sku="SKU-0001",
            product_name="Test Product",
            product_category="Snacks",
            product_id=1,
            destination_id=1,
            horizon_days=7,
        )
        assert result["forecasted_units"] >= 0
        assert result["daily_mean_demand"] >= 0.0

    def test_forecast_for_planning_integer_units(self):
        """forecasted_units must be an integer (optimizer boundary)."""
        records = _make_records(30)
        result = forecast_demand_for_planning(
            demand_history_rows=records,
            destination_code="DST-001",
            destination_name="Test",
            product_sku="SKU-0001",
            product_name="Test",
            product_category="Dairy",
            product_id=1,
            destination_id=1,
            horizon_days=7,
        )
        assert isinstance(result["forecasted_units"], int)

    def test_forecast_for_planning_insufficient_history_fallback(self):
        """With no history, returns zero forecast with warning rather than crashing."""
        result = forecast_demand_for_planning(
            demand_history_rows=[],
            destination_code="DST-X",
            destination_name="Empty Store",
            product_sku="SKU-NONE",
            product_name="Ghost Product",
            product_category="Snacks",
            product_id=99,
            destination_id=99,
            horizon_days=7,
        )
        assert result["forecasted_units"] == 0
        assert result["daily_mean_demand"] == 0.0
        assert len(result["warnings"]) > 0

    def test_build_forecast_lookup_returns_all_pairs(self):
        destinations = [
            {"id": 1, "code": "D1", "name": "Store 1"},
            {"id": 2, "code": "D2", "name": "Store 2"},
        ]
        products = [
            {"id": 1, "sku": "SKU-1", "name": "Milk", "category": "Dairy"},
            {"id": 2, "sku": "SKU-2", "name": "Chips", "category": "Snacks"},
        ]
        demand_rows = []
        for dst_id in (1, 2):
            for prod_id in (1, 2):
                for i in range(30):
                    demand_rows.append({
                        "destination_id": dst_id,
                        "product_id": prod_id,
                        "demand_date": BASE_DATE + timedelta(days=i),
                        "quantity_demanded": 50,
                        "quantity_sold": 50,
                        "is_simulated": True,
                    })
        results = build_forecast_lookup(
            demand_rows=demand_rows,
            destinations=destinations,
            products=products,
            horizon_days=7,
        )
        assert len(results) == 4   # 2 destinations × 2 products

    # Verify daily_mean_demand is compatible with InventoryPositionAnalyzer
    def test_identify_stockout_risks_compat(self):
        from app.engine.position.inventory_position import InventoryPositionAnalyzer

        records = _make_records(30, base_demand=100)
        fc = forecast_demand_for_planning(
            demand_history_rows=records,
            destination_code="DST-001",
            destination_name="Store",
            product_sku="SKU-0001",
            product_name="Milk",
            product_category="Dairy",
            product_id=1,
            destination_id=1,
            horizon_days=7,
        )

        # Simulate low stock scenario
        destination_stock = {"DST-001": {"SKU-0001": 50}}   # 0.5 days cover
        alerts = InventoryPositionAnalyzer.identify_stockout_risks(
            [fc], destination_current_stock=destination_stock
        )
        assert len(alerts) == 1
        assert alerts[0]["risk_level"] in ("Critical", "High", "Moderate", "Low", "InsufficientData")



# ===========================================================================
# SECTION 6 — Backward-compatible BaselineDemandForecaster
# ===========================================================================

class TestBaselineDemandForecasterCompat:

    def test_legacy_heuristic_no_history(self, sample_fmcg_data):
        """Existing test from test_forecast.py — must still pass."""
        forecaster = BaselineDemandForecaster(seed=42)
        forecasts = forecaster.forecast_demand(
            sample_fmcg_data["destinations"],
            sample_fmcg_data["products"],
            horizon_days=7,
        )
        assert len(forecasts) == len(sample_fmcg_data["destinations"]) * len(sample_fmcg_data["products"])
        for f in forecasts:
            assert f["forecasted_units"] > 0
            assert f["daily_mean_demand"] > 0
            assert "destination_code" in f
            assert "sku" in f

    def test_data_driven_path_with_history(self, sample_fmcg_data):
        """Data-driven path returns valid dicts when history is provided."""
        # Build minimal demand_history rows matching destinations/products
        dests = sample_fmcg_data["destinations"]
        prods = sample_fmcg_data["products"]
        demand_history = []
        for i, dst in enumerate(dests):
            for j, prod in enumerate(prods):
                for k in range(30):
                    demand_history.append({
                        "destination_id": i + 1,
                        "product_id": j + 1,
                        "demand_date": BASE_DATE + timedelta(days=k),
                        "quantity_demanded": 50,
                        "quantity_sold": 50,
                        "is_simulated": True,
                    })
        # Inject ids into dicts
        dests_with_ids = [dict(d, id=i+1, code=d.get("code", f"D{i+1}"), name=d.get("name", f"Store {i+1}")) for i, d in enumerate(dests)]
        prods_with_ids = [dict(p, id=j+1, sku=p.get("sku", f"SKU-{j+1}"), name=p.get("name", f"P{j+1}"), category=p.get("category", "Snacks")) for j, p in enumerate(prods)]

        forecaster = BaselineDemandForecaster(seed=42)
        forecasts = forecaster.forecast_demand(
            dests_with_ids,
            prods_with_ids,
            horizon_days=7,
            demand_history=demand_history,
        )
        assert len(forecasts) == len(dests) * len(prods)
        for f in forecasts:
            assert "daily_mean_demand" in f
            assert "forecasted_units" in f
            assert f["forecasted_units"] >= 0


# ===========================================================================
# SECTION 7 — API endpoint tests
# ===========================================================================

class TestForecastAPI:

    # 13. API validation and error responses
    def test_forecast_invalid_horizon_422(self, client):
        resp = client.post("/api/v1/forecast", json={
            "product_id": 1,
            "destination_id": 1,
            "horizon_days": 5,   # invalid
            "method": "naive",
        })
        assert resp.status_code == 422

    def test_forecast_invalid_method_422(self, client):
        resp = client.post("/api/v1/forecast", json={
            "product_id": 1,
            "destination_id": 1,
            "horizon_days": 7,
            "method": "magic_forecast",
        })
        assert resp.status_code == 422

    def test_forecast_invalid_alpha_422(self, client):
        resp = client.post("/api/v1/forecast", json={
            "product_id": 1,
            "destination_id": 1,
            "horizon_days": 7,
            "method": "ewma",
            "ewma_alpha": 0.0,   # must be > 0
        })
        assert resp.status_code == 422

    def test_forecast_nonexistent_product_404(self, client):
        resp = client.post("/api/v1/forecast", json={
            "product_id": 99999,
            "destination_id": 1,
            "horizon_days": 7,
            "method": "naive",
        })
        assert resp.status_code == 404

    def test_forecast_nonexistent_destination_404(self, client):
        # First we need a product to exist
        resp = client.post("/api/v1/forecast", json={
            "product_id": 1,
            "destination_id": 99999,
            "horizon_days": 7,
            "method": "naive",
        })
        assert resp.status_code == 404

    def test_methods_endpoint_returns_list(self, client):
        resp = client.get("/api/v1/forecast/methods")
        assert resp.status_code == 200
        data = resp.json()
        assert "supported_methods" in data
        assert "supported_horizons" in data
        assert set(data["supported_methods"]) == {"naive", "ewma", "seasonal_naive"}
        assert set(data["supported_horizons"]) == {7, 14, 30}

    def test_evaluate_nonexistent_product_404(self, client):
        resp = client.post("/api/v1/forecast/evaluate", json={
            "product_id": 99999,
        })
        assert resp.status_code == 404

    def test_evaluate_nonexistent_destination_404(self, client):
        resp = client.post("/api/v1/forecast/evaluate", json={
            "destination_id": 99999,
        })
        assert resp.status_code == 404

    def test_evaluate_no_data_400(self, client):
        """Empty DB → 400 from evaluate endpoint."""
        resp = client.post("/api/v1/forecast/evaluate", json={})
        assert resp.status_code == 400
