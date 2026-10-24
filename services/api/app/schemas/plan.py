"""Planning and Optimization Request and Response Schemas."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

class OptimizationParameters(BaseModel):
    transport_weight: float = Field(default=1.0, ge=0.0, description="Cost weight for transportation distance")
    stockout_penalty_weight: float = Field(default=5.0, ge=0.0, description="Penalty weight for unsatisfied demand")
    expiry_risk_weight: float = Field(default=2.5, ge=0.0, description="Penalty weight for holding near-expiry stock")
    max_solver_time_seconds: int = Field(default=10, ge=1, le=120)

class PlanRequest(BaseModel):
    dataset_version_id: Optional[int] = None
    forecast_horizon_days: int = Field(default=7, ge=1, le=30)
    parameters: OptimizationParameters = Field(default_factory=OptimizationParameters)

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
    estimated_expiry_risk_pct: float
    reasoning: Optional[str] = None

class StockoutRiskAlert(BaseModel):
    destination_code: str
    destination_name: str
    product_sku: str
    current_inventory_days: float
    forecasted_daily_demand: float
    risk_level: str  # HIGH, MEDIUM, LOW

class PlanSummaryMetrics(BaseModel):
    total_shipped_units: int
    total_transport_cost: float
    avg_expiry_risk_pct: float
    stockouts_prevented: int
    destinations_at_risk: int

class PlanResponse(BaseModel):
    run_code: str
    dataset_version: str
    forecast_identifier: str
    solver_status: str
    created_at: datetime
    metrics: PlanSummaryMetrics
    shipments: List[ShipmentSchema]
    stockout_risks: List[StockoutRiskAlert]

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
