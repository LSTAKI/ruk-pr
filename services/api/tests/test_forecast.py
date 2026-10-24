"""Tests for baseline demand forecaster."""

from app.engine.forecast.forecaster import BaselineDemandForecaster

def test_forecast_demand_structure(sample_fmcg_data):
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
