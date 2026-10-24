"""Demand Forecasting API Schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ForecastRequest(BaseModel):
    """Request body for a single product-destination forecast."""

    product_id: int = Field(..., description="Database ID of the product")
    destination_id: int = Field(..., description="Database ID of the destination")
    horizon_days: int = Field(
        default=7,
        description="Forecast horizon in days. Must be 7, 14, or 30.",
    )
    method: str = Field(
        default="ewma",
        description="Forecasting method: 'naive', 'ewma', or 'seasonal_naive'.",
    )
    ewma_alpha: float = Field(
        default=0.3,
        ge=0.01,
        le=1.0,
        description=(
            "EWMA smoothing parameter α ∈ (0, 1]. "
            "Higher values weight recent observations more heavily. "
            "Ignored for non-EWMA methods."
        ),
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description=(
            "Forecast origin date (ISO 8601). Observations after this date "
            "are excluded to prevent data leakage. Defaults to today (UTC)."
        ),
    )

    @field_validator("horizon_days")
    @classmethod
    def validate_horizon(cls, v: int) -> int:
        if v not in (7, 14, 30):
            raise ValueError("horizon_days must be 7, 14, or 30.")
        return v

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed = ("naive", "ewma", "seasonal_naive")
        if v not in allowed:
            raise ValueError(f"method must be one of {allowed}.")
        return v


class ForecastEvaluationRequest(BaseModel):
    """Request body for backtesting evaluation."""

    product_id: Optional[int] = Field(
        default=None,
        description="If provided, evaluate only this product (all destinations).",
    )
    destination_id: Optional[int] = Field(
        default=None,
        description="If provided, evaluate only this destination (all products).",
    )
    ewma_alpha: float = Field(
        default=0.3,
        ge=0.01,
        le=1.0,
        description="EWMA smoothing parameter for evaluation.",
    )
    test_fraction: float = Field(
        default=0.2,
        ge=0.05,
        le=0.5,
        description=(
            "Fraction of observations reserved for the test partition. "
            "Default 0.2 = last 20% of history used as holdout."
        ),
    )
    min_test_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Minimum number of test-period observations.",
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description="Evaluation origin date. Future observations excluded.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DailyForecastValue(BaseModel):
    """A single forecast day."""

    date: date
    value: float = Field(..., description="Forecast demand (non-negative float, 2 dp).")


class ForecastResponse(BaseModel):
    """Response for a single product-destination forecast."""

    product_id: int
    product_sku: str
    destination_id: int
    destination_code: str
    generated_at: datetime
    horizon_days: int
    method: str
    method_available: bool
    unavailability_reason: Optional[str] = None
    daily_forecasts: List[DailyForecastValue]
    total_demand: float = Field(
        ...,
        description="Sum of daily forecast values over the horizon (float).",
    )
    daily_mean_demand: float = Field(
        ...,
        description="Mean daily demand over the horizon (used for stockout risk calc).",
    )
    forecasted_units: int = Field(
        ...,
        description=(
            "Integer-rounded total demand for use by the optimizer. "
            "Rounding policy: round() (banker's rounding)."
        ),
    )
    history_observations_used: int
    warnings: List[str]
    is_simulated_data: bool


class MethodEvalResult(BaseModel):
    """Per-method backtesting result for one series."""

    method: str
    method_available: bool
    unavailability_reason: Optional[str] = None
    mae: Optional[float] = Field(None, description="Mean Absolute Error.")
    wape_pct: Optional[float] = Field(
        None,
        description=(
            "Weighted Absolute Percentage Error (%). "
            "None when sum of actual demand in test period is zero."
        ),
    )
    wape_unavailable_reason: Optional[str] = None
    n_evaluated: int
    evaluation_start: Optional[date] = None
    evaluation_end: Optional[date] = None


class SeriesEvalResult(BaseModel):
    """Backtesting results for one product-destination series."""

    product_id: Optional[int] = None
    destination_id: Optional[int] = None
    product_sku: Optional[str] = None
    destination_code: Optional[str] = None
    train_observations: int
    test_observations: int
    total_observations: int
    evaluation_start: Optional[date] = None
    evaluation_end: Optional[date] = None
    methods: Dict[str, MethodEvalResult]
    warnings: List[str]


class AggregateMethodSummary(BaseModel):
    """Aggregate accuracy summary for one method across all evaluated series."""

    method: str
    series_with_method: int
    mae_mean: Optional[float] = None
    mae_min: Optional[float] = None
    mae_max: Optional[float] = None
    wape_mean_pct: Optional[float] = None
    wape_min_pct: Optional[float] = None
    wape_max_pct: Optional[float] = None
    wape_series_with_zero_actuals: int = 0


class ForecastEvaluationResponse(BaseModel):
    """Response for a backtesting evaluation request."""

    n_series_evaluated: int
    total_observations_evaluated: int
    aggregate: Dict[str, AggregateMethodSummary]
    caveats: List[str]
    series: List[SeriesEvalResult]
