"""Schemas package."""
from app.schemas.common import HealthResponse, ErrorResponse
from app.schemas.inventory import (
    WarehouseSchema,
    DestinationSchema,
    ProductSchema,
    InventoryItemSchema,
    InventoryOverviewResponse,
    RouteSchema,
    RouteListResponse,
    DailyDemandHistorySchema,
    DemandHistoryResponse,
    InventoryBatchListResponse,
)
from app.schemas.plan import (
    OptimizationParameters,
    PlanRequest,
    PlanResponse,
    ShipmentSchema,
    StockoutRiskAlert,
    PlanSummaryMetrics,
    PlanningRunListItem,
    PlanningRunListResponse,
)
from app.schemas.scenario import ScenarioCreate, ScenarioResponse

__all__ = [
    "HealthResponse",
    "ErrorResponse",
    "WarehouseSchema",
    "DestinationSchema",
    "ProductSchema",
    "InventoryItemSchema",
    "InventoryOverviewResponse",
    "RouteSchema",
    "RouteListResponse",
    "DailyDemandHistorySchema",
    "DemandHistoryResponse",
    "InventoryBatchListResponse",
    "OptimizationParameters",
    "PlanRequest",
    "PlanResponse",
    "ShipmentSchema",
    "StockoutRiskAlert",
    "PlanSummaryMetrics",
    "PlanningRunListItem",
    "PlanningRunListResponse",
    "ScenarioCreate",
    "ScenarioResponse",
]
