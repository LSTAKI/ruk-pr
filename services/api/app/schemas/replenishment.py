"""Replenishment and Inventory Position API Schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Safety Stock Schemas
# ---------------------------------------------------------------------------

class SafetyStockConfigSchema(BaseModel):
    """Safety-stock policy configuration."""

    service_level_z: float = Field(
        default=1.65,
        ge=0.0,
        le=4.0,
        description=(
            "Service-level z-factor. Common values: "
            "1.04 (85%), 1.28 (90%), 1.65 (95%, default), 2.33 (99%). "
            "This is a configuration parameter, NOT a guaranteed service level."
        ),
    )
    fallback_factor: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of mean-demand × lead-time used as safety stock "
            "when σ_d cannot be reliably estimated."
        ),
    )
    min_safety_stock_units: float = Field(
        default=0.0,
        ge=0.0,
        description="Absolute minimum safety-stock floor (units).",
    )


class SafetyStockResultSchema(BaseModel):
    """Safety stock calculation result."""

    safety_stock_units: float
    safety_stock_int: int = Field(..., description="Ceiling-rounded units for replenishment use.")
    method_used: str = Field(..., description="'formula', 'fallback', or 'zero'.")
    mean_daily_demand: float
    stddev_daily_demand: Optional[float] = None
    lead_time_days: float
    observations_used: int
    warnings: List[str]
    is_simulated_data: bool


# ---------------------------------------------------------------------------
# Replenishment Schemas
# ---------------------------------------------------------------------------

class ReplenishmentRequest(BaseModel):
    """Request for replenishment requirements for a product-destination pair."""

    product_id: int
    destination_id: int
    warehouse_id: Optional[int] = Field(
        default=None,
        description="Preferred supply warehouse. If None, all warehouses are evaluated.",
    )
    safety_stock_config: SafetyStockConfigSchema = Field(
        default_factory=SafetyStockConfigSchema,
    )
    forecast_method: str = Field(
        default="ewma",
        description="Forecasting method: 'naive', 'ewma', or 'seasonal_naive'.",
    )
    ewma_alpha: float = Field(
        default=0.3,
        ge=0.01,
        le=1.0,
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description="Planning date. Future observations excluded. Defaults to today.",
    )

    @field_validator("forecast_method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in ("naive", "ewma", "seasonal_naive"):
            raise ValueError("forecast_method must be 'naive', 'ewma', or 'seasonal_naive'.")
        return v


class ReplenishmentRequirementSchema(BaseModel):
    """Replenishment requirement for one product-destination pair."""

    product_id: int
    product_sku: str
    product_name: str
    destination_id: int
    destination_code: str
    destination_name: str

    # Route and lead time
    lead_time_days: float
    warehouse_code: Optional[str] = None
    route_selection_reason: str

    # Demand
    daily_mean_demand: float
    lead_time_demand: float = Field(
        ...,
        description="daily_mean_demand × lead_time_days (float, not rounded).",
    )
    forecast_method: str
    forecast_warnings: List[str]

    # Safety stock
    safety_stock: SafetyStockResultSchema

    # Replenishment formulas
    replenishment_threshold: float = Field(
        ...,
        description="lead_time_demand + safety_stock_units",
    )

    # Inventory position (documented gaps)
    destination_usable_units: int = Field(
        ...,
        description="Destination on-hand stock (0 until DestinationInventory table added).",
    )
    incoming_committed_units: int = Field(
        ...,
        description="In-transit committed stock (0 until ConfirmedDispatch table added).",
    )
    projected_position: float = Field(
        ...,
        description="destination_usable + incoming_committed.",
    )

    # Replenishment
    gross_replenishment: float = Field(
        ...,
        description="max(0, threshold - projected_position)",
    )
    replenishment_qty: int = Field(
        ...,
        description="ceil(gross_replenishment) — non-negative integer.",
    )

    # Risk
    cover_days: Optional[float] = Field(
        None,
        description="Estimated days of inventory cover at destination. None if demand=0.",
    )
    safety_stock_days: Optional[float] = None
    risk_category: str = Field(
        ...,
        description=(
            "Critical / High / Moderate / Low / InsufficientData. "
            "NOT a calibrated stockout probability."
        ),
    )

    # Explanation
    reason_codes: List[str]
    explanation: str
    warnings: List[str]
    history_observations_used: int


class ReplenishmentResponse(BaseModel):
    """Response for a single product-destination replenishment request."""
    generated_at: datetime
    product_id: int
    destination_id: int
    warehouses_evaluated: List[str]
    requirements: List[ReplenishmentRequirementSchema]


class ReplenishmentSummaryRequest(BaseModel):
    """Request body for batch replenishment summary."""

    warehouse_id: Optional[int] = Field(
        default=None,
        description="Filter to a specific supply warehouse.",
    )
    product_id: Optional[int] = Field(
        default=None,
        description="Filter to a specific product.",
    )
    destination_id: Optional[int] = Field(
        default=None,
        description="Filter to a specific destination.",
    )
    safety_stock_config: SafetyStockConfigSchema = Field(
        default_factory=SafetyStockConfigSchema,
    )
    forecast_method: str = Field(default="ewma")
    ewma_alpha: float = Field(default=0.3, ge=0.01, le=1.0)
    risk_filter: Optional[str] = Field(
        default=None,
        description="Only return items at or above this risk level: Critical, High, Moderate.",
    )
    as_of_date: Optional[date] = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ReplenishmentSummaryResponse(BaseModel):
    """Paginated replenishment summary across all product-destination pairs."""
    generated_at: datetime
    total: int
    limit: int
    offset: int
    warehouses_evaluated: List[str]
    as_of_date: date
    requirements: List[ReplenishmentRequirementSchema]
    # Aggregate stats
    total_replenishment_units: int
    critical_count: int
    high_count: int
    moderate_count: int
    low_count: int
    insufficient_data_count: int
    caveats: List[str]


# ---------------------------------------------------------------------------
# Optimizer Contract Schema
# ---------------------------------------------------------------------------

class OptimizerContractItem(BaseModel):
    """Single item in the optimizer integration contract."""

    product_id: int
    product_sku: str
    destination_id: int
    destination_code: str

    replenishment_qty: int = Field(
        ...,
        description=(
            "Replenishment signal for the optimizer. "
            "NOT a supply guarantee — warehouse stock is a separate constraint."
        ),
    )
    gross_replenishment: float
    lead_time_demand: float
    daily_mean_demand: float
    lead_time_days: float
    safety_stock_units: int
    safety_stock_method: str
    projected_position: float
    destination_stock_tracked: bool = Field(
        ...,
        description="False until DestinationInventory table is added (GAP-1).",
    )
    risk_category: str
    warnings: List[str]
    history_used: int
    forecast_method: str


class OptimizerContractResponse(BaseModel):
    """Full optimizer integration contract for a planning run."""
    generated_at: datetime
    n_items: int
    caveats: List[str]
    items: List[OptimizerContractItem]
