"""Transportation routes route handlers."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Route, Warehouse, Destination
from app.schemas.inventory import RouteSchema, RouteListResponse

router = APIRouter(prefix="/routes", tags=["Routes"])

@router.get("", response_model=RouteListResponse)
def list_routes(
    origin_warehouse_id: Optional[int] = Query(None, description="Filter by origin warehouse ID"),
    destination_id: Optional[int] = Query(None, description="Filter by destination ID"),
    is_active: Optional[bool] = Query(None, description="Filter by route active status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Lists transportation routes with distances, unit freight costs, and lead times.
    """
    query = (
        db.query(Route, Warehouse.code, Destination.code, Destination.name)
        .join(Warehouse, Route.origin_warehouse_id == Warehouse.id)
        .join(Destination, Route.destination_id == Destination.id)
    )

    if origin_warehouse_id is not None:
        query = query.filter(Route.origin_warehouse_id == origin_warehouse_id)
    if destination_id is not None:
        query = query.filter(Route.destination_id == destination_id)
    if is_active is not None:
        query = query.filter(Route.is_active == is_active)

    total = query.count()
    records = query.order_by(Route.id.asc()).offset(offset).limit(limit).all()

    routes = [
        RouteSchema(
            id=r.id,
            origin_warehouse_id=r.origin_warehouse_id,
            destination_id=r.destination_id,
            origin_warehouse_code=wh_code,
            destination_code=dst_code,
            destination_name=dst_name,
            unit_transport_cost=r.unit_transport_cost,
            lead_time_days=r.lead_time_days,
            distance_km=r.distance_km,
            is_active=r.is_active,
        )
        for r, wh_code, dst_code, dst_name in records
    ]

    return RouteListResponse(
        total=total,
        limit=limit,
        offset=offset,
        routes=routes,
    )

@router.get("/{route_id}", response_model=RouteSchema)
def get_route(route_id: int, db: Session = Depends(get_db)):
    """Retrieves single route details."""
    record = (
        db.query(Route, Warehouse.code, Destination.code, Destination.name)
        .join(Warehouse, Route.origin_warehouse_id == Warehouse.id)
        .join(Destination, Route.destination_id == Destination.id)
        .filter(Route.id == route_id)
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route {route_id} not found."
        )

    r, wh_code, dst_code, dst_name = record
    return RouteSchema(
        id=r.id,
        origin_warehouse_id=r.origin_warehouse_id,
        destination_id=r.destination_id,
        origin_warehouse_code=wh_code,
        destination_code=dst_code,
        destination_name=dst_name,
        unit_transport_cost=r.unit_transport_cost,
        lead_time_days=r.lead_time_days,
        distance_km=r.distance_km,
        is_active=r.is_active,
    )
