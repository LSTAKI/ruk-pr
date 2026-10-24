"""Inventory, Warehouse, Product, Batch, and Route Schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

class WarehouseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    city: str
    state: str
    capacity_units: int
    daily_dispatch_capacity_units: int = 15000
    latitude: float
    longitude: float

class DestinationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    channel_type: str
    city: str
    state: str
    daily_receiving_capacity_units: int = 3000
    latitude: float
    longitude: float

class ProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str
    unit_of_measure: str = "units"
    shelf_life_days: int
    unit_cost: float
    unit_price: float
    holding_cost_per_day: float = 0.02
    lost_sales_penalty: float = 5.0
    storage_temp_c: float
    weight_kg: float

class InventoryItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    product_id: int
    batch_lot: str
    on_hand_units: int
    reserved_units: int
    available_units: Optional[int] = None
    usable_units: Optional[int] = None
    unit_cost: float = 0.0
    expiry_date: datetime
    received_date: Optional[datetime] = None
    batch_status: str = "AVAILABLE"
    warehouse_code: Optional[str] = None
    product_sku: Optional[str] = None
    product_name: Optional[str] = None

class InventoryOverviewResponse(BaseModel):
    total_products: int
    total_warehouses: int
    total_destinations: int
    total_units_on_hand: int
    total_units_reserved: int
    total_units_available: int
    total_units_usable: int
    dataset_version: str
    warehouses: List[WarehouseSchema]
    products: List[ProductSchema]

class RouteSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origin_warehouse_id: int
    destination_id: int
    origin_warehouse_code: Optional[str] = None
    destination_code: Optional[str] = None
    destination_name: Optional[str] = None
    unit_transport_cost: float
    lead_time_days: float
    distance_km: float
    is_active: bool

class RouteListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    routes: List[RouteSchema]

class DailyDemandHistorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    destination_id: int
    product_id: int
    destination_code: Optional[str] = None
    destination_name: Optional[str] = None
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    demand_date: datetime
    quantity_demanded: int
    quantity_sold: int
    is_simulated: bool

class DemandHistoryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    records: List[DailyDemandHistorySchema]

class InventoryBatchListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    batches: List[InventoryItemSchema]
