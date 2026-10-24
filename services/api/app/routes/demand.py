"""Demand History route handlers."""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import DailyDemandHistory, Destination, Product
from app.schemas.inventory import DailyDemandHistorySchema, DemandHistoryResponse

router = APIRouter(prefix="/demand", tags=["Demand"])

@router.get("/history", response_model=DemandHistoryResponse)
def get_demand_history(
    destination_id: Optional[int] = Query(None, description="Filter by destination ID"),
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Fetches empirical product-destination demand consumption records with filtering and pagination.
    """
    query = (
        db.query(DailyDemandHistory, Destination.code, Destination.name, Product.sku, Product.name)
        .join(Destination, DailyDemandHistory.destination_id == Destination.id)
        .join(Product, DailyDemandHistory.product_id == Product.id)
    )

    if destination_id is not None:
        query = query.filter(DailyDemandHistory.destination_id == destination_id)
    if product_id is not None:
        query = query.filter(DailyDemandHistory.product_id == product_id)
    if start_date is not None:
        query = query.filter(DailyDemandHistory.demand_date >= start_date)
    if end_date is not None:
        query = query.filter(DailyDemandHistory.demand_date <= end_date)

    total = query.count()
    records = (
        query.order_by(DailyDemandHistory.demand_date.desc(), DailyDemandHistory.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result_items = [
        DailyDemandHistorySchema(
            id=d.id,
            destination_id=d.destination_id,
            product_id=d.product_id,
            destination_code=dst_code,
            destination_name=dst_name,
            product_sku=prod_sku,
            product_name=prod_name,
            demand_date=d.demand_date,
            quantity_demanded=d.quantity_demanded,
            quantity_sold=d.quantity_sold,
            is_simulated=d.is_simulated,
        )
        for d, dst_code, dst_name, prod_sku, prod_name in records
    ]

    return DemandHistoryResponse(
        total=total,
        limit=limit,
        offset=offset,
        records=result_items,
    )
