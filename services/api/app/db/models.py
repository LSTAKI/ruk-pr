"""SQLAlchemy 2.0 Database Models for StockWise AI."""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Text,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from app.db.session import Base

class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_tag = Column(String(64), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    random_seed = Column(Integer, default=42, nullable=False)
    parameters = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    inventory_items = relationship("InventoryItem", back_populates="dataset_version", cascade="all, delete-orphan")
    planning_runs = relationship("PlanningRun", back_populates="dataset_version")

class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    city = Column(String(64), nullable=False)
    state = Column(String(64), nullable=False)
    capacity_units = Column(Integer, nullable=False)  # Total physical volumetric capacity
    daily_dispatch_capacity_units = Column(Integer, nullable=False, default=15000)  # Max daily dispatch limit
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    inventory_items = relationship("InventoryItem", back_populates="warehouse", cascade="all, delete-orphan")
    shipments = relationship("ShipmentRecommendation", back_populates="source_warehouse")
    routes = relationship("Route", back_populates="origin_warehouse", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("capacity_units >= 0", name="ck_warehouse_capacity_positive"),
        CheckConstraint("daily_dispatch_capacity_units >= 0", name="ck_warehouse_dispatch_capacity_positive"),
    )

class Destination(Base):
    __tablename__ = "destinations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    channel_type = Column(String(64), nullable=False)  # supermarket, convenience, wholesaler
    city = Column(String(64), nullable=False)
    state = Column(String(64), nullable=False)
    daily_receiving_capacity_units = Column(Integer, nullable=False, default=3000)  # Max intake limit per day
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipments = relationship("ShipmentRecommendation", back_populates="destination")
    routes = relationship("Route", back_populates="destination", cascade="all, delete-orphan")
    demand_history = relationship("DailyDemandHistory", back_populates="destination", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("daily_receiving_capacity_units >= 0", name="ck_destination_receiving_capacity_positive"),
    )

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    category = Column(String(64), nullable=False)  # Dairy, Beverages, Snacks, Personal Care
    unit_of_measure = Column(String(32), default="units", nullable=False)
    shelf_life_days = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    holding_cost_per_day = Column(Float, default=0.02, nullable=False)
    lost_sales_penalty = Column(Float, default=5.0, nullable=False)
    storage_temp_c = Column(Float, default=20.0)
    weight_kg = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    inventory_items = relationship("InventoryItem", back_populates="product", cascade="all, delete-orphan")
    shipments = relationship("ShipmentRecommendation", back_populates="product")
    demand_history = relationship("DailyDemandHistory", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("shelf_life_days > 0", name="ck_product_shelf_life_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_product_cost_non_negative"),
        CheckConstraint("unit_price >= 0", name="ck_product_price_non_negative"),
        CheckConstraint("holding_cost_per_day >= 0", name="ck_product_holding_cost_non_negative"),
    )

class InventoryItem(Base):
    """
    Source inventory batch representation.
    Tracks physical on-hand, reservations, unit cost, status, and expiry schedule.
    """
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    batch_lot = Column(String(64), nullable=False, index=True)
    on_hand_units = Column(Integer, nullable=False, default=0)
    reserved_units = Column(Integer, nullable=False, default=0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    expiry_date = Column(DateTime, nullable=False)
    received_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    batch_status = Column(String(32), nullable=False, default="AVAILABLE")  # AVAILABLE, QUARANTINED, EXPIRED, DEPLETED
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset_version = relationship("DatasetVersion", back_populates="inventory_items")
    warehouse = relationship("Warehouse", back_populates="inventory_items")
    product = relationship("Product", back_populates="inventory_items")

    __table_args__ = (
        CheckConstraint("on_hand_units >= 0", name="ck_inventory_on_hand_non_negative"),
        CheckConstraint("reserved_units >= 0", name="ck_inventory_reserved_non_negative"),
        CheckConstraint("reserved_units <= on_hand_units", name="ck_inventory_reserved_lte_on_hand"),
        UniqueConstraint("dataset_version_id", "warehouse_id", "product_id", "batch_lot", name="uq_inventory_batch_unique"),
        Index("ix_inventory_wh_prod", "warehouse_id", "product_id"),
        Index("ix_inventory_expiry", "expiry_date"),
    )

class Route(Base):
    """
    Transportation route connecting origin warehouse to destination retail store.
    Stores freight cost, lead time, distance, and active availability.
    """
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    origin_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, index=True)
    destination_id = Column(Integer, ForeignKey("destinations.id"), nullable=False, index=True)
    unit_transport_cost = Column(Float, nullable=False)
    lead_time_days = Column(Float, nullable=False, default=1.0)
    distance_km = Column(Float, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    origin_warehouse = relationship("Warehouse", back_populates="routes")
    destination = relationship("Destination", back_populates="routes")

    __table_args__ = (
        CheckConstraint("unit_transport_cost >= 0", name="ck_route_cost_non_negative"),
        CheckConstraint("lead_time_days >= 0", name="ck_route_lead_time_non_negative"),
        CheckConstraint("distance_km >= 0", name="ck_route_distance_non_negative"),
        UniqueConstraint("origin_warehouse_id", "destination_id", name="uq_route_origin_destination"),
        Index("ix_route_origin_dest", "origin_warehouse_id", "destination_id"),
    )

class DailyDemandHistory(Base):
    """
    Empirical product-destination historical consumption records.
    Provides verified baseline datasets for demand forecasting and safety stock calibration.
    """
    __tablename__ = "daily_demand_history"

    id = Column(Integer, primary_key=True, index=True)
    destination_id = Column(Integer, ForeignKey("destinations.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    demand_date = Column(DateTime, nullable=False, index=True)
    quantity_demanded = Column(Integer, nullable=False)
    quantity_sold = Column(Integer, nullable=False)
    is_simulated = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    destination = relationship("Destination", back_populates="demand_history")
    product = relationship("Product", back_populates="demand_history")

    __table_args__ = (
        CheckConstraint("quantity_demanded >= 0", name="ck_demand_quantity_demanded_non_negative"),
        CheckConstraint("quantity_sold >= 0", name="ck_demand_quantity_sold_non_negative"),
        UniqueConstraint("destination_id", "product_id", "demand_date", name="uq_daily_demand_dest_prod_date"),
        Index("ix_demand_dest_prod_date", "destination_id", "product_id", "demand_date"),
    )

class PlanningRun(Base):
    """Records run metadata, forecast identifier, parameters, and solver status."""
    __tablename__ = "planning_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_code = Column(String(64), unique=True, index=True, nullable=False)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=False)
    forecast_identifier = Column(String(128), nullable=False)
    optimization_parameters = Column(JSON, default=dict)
    solver_status = Column(String(32), nullable=False)  # INITIALIZED, OPTIMAL, FEASIBLE, INFEASIBLE
    total_transport_cost = Column(Float, default=0.0)
    total_shipped_units = Column(Integer, default=0)
    stockout_risk_count = Column(Integer, default=0)
    status = Column(String(32), default="COMPLETED")
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset_version = relationship("DatasetVersion", back_populates="planning_runs")
    shipments = relationship("ShipmentRecommendation", back_populates="planning_run", cascade="all, delete-orphan")

class ShipmentRecommendation(Base):
    """Individual shipping decisions generated by planning runs."""
    __tablename__ = "shipment_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    planning_run_id = Column(Integer, ForeignKey("planning_runs.id"), nullable=False)
    source_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    destination_id = Column(Integer, ForeignKey("destinations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    recommended_units = Column(Integer, nullable=False)
    unit_transport_cost = Column(Float, nullable=False)
    total_transport_cost = Column(Float, nullable=False)
    estimated_expiry_risk_pct = Column(Float, default=0.0)
    priority_score = Column(Float, default=1.0)
    reasoning = Column(Text, nullable=True)

    planning_run = relationship("PlanningRun", back_populates="shipments")
    source_warehouse = relationship("Warehouse", back_populates="shipments")
    destination = relationship("Destination", back_populates="shipments")
    product = relationship("Product", back_populates="shipments")

    __table_args__ = (
        CheckConstraint("recommended_units >= 0", name="ck_shipment_units_non_negative"),
        CheckConstraint("unit_transport_cost >= 0", name="ck_shipment_unit_cost_non_negative"),
    )
