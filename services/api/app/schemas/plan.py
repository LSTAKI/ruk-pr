"""Planning and Optimization Request and Response Schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OptimizationParameters(BaseModel):
    transport_weight: float = Field(
        default=1.0, ge=0.0, description="Cost weight for transportation freight ($/unit multiplier)"
    )
    stockout_penalty_weight: float = Field(
        default=5.0, ge=0.0, description="Penalty multiplier for unsatisfied demand (lost-sales multiplier)"
    )
    expiry_risk_weight: float = Field(
        default=2.5, ge=0.0, description="Weight for holding near-expiry stock"
    )
    lead_time_penalty_weight: float = Field(
        default=0.20,
        ge=0.0,
        description="Monetary penalty per transit day per unit ($/day/unit) representing transit holding/freshness cost",
    )
    min_fulfillment_rate: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum network fulfillment rate required under Cost-First (default 0.80 = 80%). Set to 0.0 only for unconstrained cost-first.",
    )
    allow_unconstrained_cost_first: bool = Field(
        default=False,
        description="If True, permits cost-first optimization without a fulfillment rate floor.",
    )
    min_arrival_shelf_life_days: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum remaining shelf life required upon arrival at destination (days).",
    )
    max_solver_time_seconds: int = Field(default=10, ge=1, le=120)
    profile: str = Field(
        default="balanced",
        description="Optimization profile: 'cost_first', 'service_first', or 'balanced'",
    )
    max_lead_time_days: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Delivery cutoff: routes exceeding this lead time are excluded.",
    )
    use_replenishment_engine: bool = Field(
        default=True,
        description="If True, uses safety-stock replenishment requirements as demand signal.",
    )
    ewma_alpha: float = Field(default=0.3, ge=0.01, le=1.0)
    service_level_z: float = Field(default=1.65, ge=0.0, le=4.0)

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, v: str) -> str:
        low = v.lower()
        if low not in ("cost_first", "service_first", "balanced"):
            raise ValueError("profile must be 'cost_first', 'service_first', or 'balanced'")
        return low


class PlanRequest(BaseModel):
    dataset_version_id: Optional[int] = None
    forecast_horizon_days: int = Field(default=7, ge=1, le=30)
    parameters: OptimizationParameters = Field(default_factory=OptimizationParameters)
    optimization_profile: Optional[str] = Field(
        default=None,
        description="Direct shortcut for parameters.profile ('cost_first', 'service_first', 'balanced')",
    )
    max_lead_time_days: Optional[float] = Field(
        default=None,
        description="Direct shortcut for parameters.max_lead_time_days",
    )
    min_fulfillment_rate: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Direct shortcut for parameters.min_fulfillment_rate",
    )
    allow_unconstrained_cost_first: Optional[bool] = Field(
        default=None,
        description="Direct shortcut for parameters.allow_unconstrained_cost_first",
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description="Planning date. Future observations excluded.",
    )


class ShipmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_warehouse_code: str
    destination_code: str
    destination_name: str
    product_sku: str
    product_name: str
    recommended_units: int
    unit_transport_cost: float
    total_transport_cost: float
    estimated_expiry_risk_pct: Optional[float] = None
    lead_time_days: Optional[float] = 1.0
    reasoning: Optional[str] = None


class StockoutRiskAlert(BaseModel):
    destination_code: str
    destination_name: str
    product_sku: str
    current_inventory_days: float
    forecasted_daily_demand: float
    risk_level: str  # Critical, High, Moderate, Low


class UnmetDemandSchema(BaseModel):
    destination_code: str
    destination_name: str
    product_sku: str
    product_name: str
    demanded_units: int
    fulfilled_units: int
    unmet_units: int
    risk_category: str


class BaselineComparisonSchema(BaseModel):
    baseline_total_units: int
    baseline_total_cost: float
    baseline_unmet_units: int
    baseline_fulfillment_rate: float
    optimized_total_units: int
    optimized_total_cost: float
    optimized_unmet_units: int
    optimized_fulfillment_rate: float
    units_difference: int
    cost_difference: float
    fulfillment_rate_difference: float


class VerificationSummarySchema(BaseModel):
    is_feasible: bool
    violations_count: int
    violations: List[str]
    recalculated_cost: float
    recalculated_units: int
    recalculated_fulfilled: int
    recalculated_unmet: int


class PlanSummaryMetrics(BaseModel):
    total_shipped_units: int
    total_transport_cost: float
    avg_expiry_risk_pct: Optional[float] = None
    expiry_waste_modeled: bool = False
    stockouts_prevented: int
    destinations_at_risk: int
    total_demanded_units: Optional[int] = 0
    total_unmet_units: Optional[int] = 0
    fulfillment_rate: Optional[float] = 1.0
    min_fulfillment_target_met: Optional[bool] = None
    solver_runtime_seconds: Optional[float] = 0.0


class PlanResponse(BaseModel):
    run_code: str
    dataset_version: str
    forecast_identifier: str
    solver_status: str
    status_message: Optional[str] = None
    created_at: datetime
    metrics: PlanSummaryMetrics
    shipments: List[ShipmentSchema]
    stockout_risks: List[StockoutRiskAlert]
    unmet_demands: List[UnmetDemandSchema] = Field(default_factory=list)
    baseline_comparison: Optional[BaselineComparisonSchema] = None
    verification: Optional[VerificationSummarySchema] = None
    data_quality_warnings: List[str] = Field(default_factory=list)
    optimization_profile: str = "balanced"


class PlanningRunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_code: str
    dataset_version_id: int
    forecast_identifier: str
    solver_status: str
    total_transport_cost: float
    total_shipped_units: int
    stockout_risk_count: int
    status: str
    created_at: datetime


class PlanningRunListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    runs: List[PlanningRunListItem]
