"""Inventory, Warehouse, Product, and Batch route handlers."""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.db.models import Warehouse, Product, Destination, InventoryItem, DatasetVersion
from app.schemas.inventory import (
    WarehouseSchema,
    DestinationSchema,
    ProductSchema,
    InventoryItemSchema,
    InventoryOverviewResponse,
    InventoryBatchListResponse,
)
from app.engine.position.inventory_position import InventoryPositionAnalyzer

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("/overview", response_model=InventoryOverviewResponse)
def get_inventory_overview(db: Session = Depends(get_db)):
    """
    Fetches high-level FMCG network inventory status with formal inventory accounting:
    On-Hand, Reserved, Available, and Usable units.
    """
    active_version = (
        db.query(DatasetVersion)
        .filter(DatasetVersion.is_active == True)
        .order_by(DatasetVersion.id.desc())
        .first()
    )
    version_tag = active_version.version_tag if active_version else "unseeded"

    total_prods = db.query(Product).count()
    total_wh = db.query(Warehouse).count()
    total_dst = db.query(Destination).count()

    # Query all active inventory items
    query = db.query(InventoryItem)
    if active_version:
        query = query.filter(InventoryItem.dataset_version_id == active_version.id)
    items = query.all()

    total_on_hand = 0
    total_reserved = 0
    total_available = 0
    total_usable = 0
    now = datetime.utcnow()

    for item in items:
        batch_dict = {
            "batch_lot": item.batch_lot,
            "on_hand_units": item.on_hand_units,
            "reserved_units": item.reserved_units,
            "expiry_date": item.expiry_date,
            "batch_status": item.batch_status,
        }
        eval_result = InventoryPositionAnalyzer.evaluate_batch_accounting(batch_dict, as_of_date=now)
        total_on_hand += eval_result["on_hand_units"]
        total_reserved += eval_result["reserved_units"]
        total_available += eval_result["available_units"]
        total_usable += eval_result["usable_units"]

    warehouses = db.query(Warehouse).all()
    products = db.query(Product).all()

    return InventoryOverviewResponse(
        total_products=total_prods,
        total_warehouses=total_wh,
        total_destinations=total_dst,
        total_units_on_hand=total_on_hand,
        total_units_reserved=total_reserved,
        total_units_available=total_available,
        total_units_usable=total_usable,
        dataset_version=version_tag,
        warehouses=[WarehouseSchema.model_validate(w) for w in warehouses],
        products=[ProductSchema.model_validate(p) for p in products],
    )

@router.get("/warehouses", response_model=List[WarehouseSchema])
def list_warehouses(db: Session = Depends(get_db)):
    """Lists all regional distribution centers."""
    return db.query(Warehouse).all()

@router.get("/destinations", response_model=List[DestinationSchema])
def list_destinations(
    channel_type: Optional[str] = Query(None, description="Filter by channel: supermarket, convenience, wholesaler"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lists retail destinations with optional channel filtering and pagination."""
    query = db.query(Destination)
    if channel_type:
        query = query.filter(Destination.channel_type == channel_type)
    return query.offset(offset).limit(limit).all()

@router.get("/products", response_model=List[ProductSchema])
def list_products(
    category: Optional[str] = Query(None, description="Filter by product category"),
    db: Session = Depends(get_db),
):
    """Lists FMCG catalog products."""
    query = db.query(Product)
    if category:
        query = query.filter(Product.category == category)
    return query.all()

@router.get("/batches", response_model=InventoryBatchListResponse)
def list_inventory_batches(
    warehouse_id: Optional[int] = Query(None, description="Filter by warehouse ID"),
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    batch_status: Optional[str] = Query(None, description="Filter by status: AVAILABLE, QUARANTINED, EXPIRED, DEPLETED"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Lists inventory batches with pagination and rich accounting metrics (on-hand, reserved, usable).
    """
    query = (
        db.query(InventoryItem, Warehouse.code, Product.sku, Product.name)
        .join(Warehouse, InventoryItem.warehouse_id == Warehouse.id)
        .join(Product, InventoryItem.product_id == Product.id)
    )

    if warehouse_id is not None:
        query = query.filter(InventoryItem.warehouse_id == warehouse_id)
    if product_id is not None:
        query = query.filter(InventoryItem.product_id == product_id)
    if batch_status is not None:
        query = query.filter(InventoryItem.batch_status == batch_status.upper())

    total = query.count()
    records = query.order_by(InventoryItem.expiry_date.asc()).offset(offset).limit(limit).all()

    now = datetime.utcnow()
    batches = []
    for item, wh_code, sku, prod_name in records:
        batch_dict = {
            "batch_lot": item.batch_lot,
            "on_hand_units": item.on_hand_units,
            "reserved_units": item.reserved_units,
            "expiry_date": item.expiry_date,
            "batch_status": item.batch_status,
        }
        eval_res = InventoryPositionAnalyzer.evaluate_batch_accounting(batch_dict, as_of_date=now)

        batches.append(
            InventoryItemSchema(
                id=item.id,
                warehouse_id=item.warehouse_id,
                product_id=item.product_id,
                batch_lot=item.batch_lot,
                on_hand_units=item.on_hand_units,
                reserved_units=item.reserved_units,
                available_units=eval_res["available_units"],
                usable_units=eval_res["usable_units"],
                unit_cost=item.unit_cost,
                expiry_date=item.expiry_date,
                received_date=item.received_date,
                batch_status=item.batch_status,
                warehouse_code=wh_code,
                product_sku=sku,
                product_name=prod_name,
            )
        )

    return InventoryBatchListResponse(
        total=total,
        limit=limit,
        offset=offset,
        batches=batches,
    )
