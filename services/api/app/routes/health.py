"""Health check route handlers."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.db.models import DatasetVersion
from app.schemas.common import HealthResponse
from app.config import settings

router = APIRouter(tags=["Health"])

@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)):
    """Health check verifying database connectivity and active dataset version."""
    db_ok = False
    active_version = None

    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        latest_ver = (
            db.query(DatasetVersion)
            .filter(DatasetVersion.is_active == True)
            .order_by(DatasetVersion.id.desc())
            .first()
        )
        if latest_ver:
            active_version = latest_ver.version_tag
    except Exception:
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        environment=settings.env,
        database_connected=db_ok,
        version="0.1.0",
        active_dataset_version=active_version,
    )
