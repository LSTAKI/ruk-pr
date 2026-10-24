"""Scenario management routes."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import DatasetVersion
from app.schemas.scenario import ScenarioCreate, ScenarioResponse

router = APIRouter(prefix="/scenarios", tags=["Scenarios"])

@router.get("", response_model=List[ScenarioResponse])
def list_scenarios(db: Session = Depends(get_db)):
    versions = db.query(DatasetVersion).order_by(DatasetVersion.id.desc()).all()
    return [
        ScenarioResponse(
            id=v.id,
            name=v.description or v.version_tag,
            version_tag=v.version_tag,
            description=v.description,
            parameters=v.parameters or {},
            is_active=v.is_active,
        )
        for v in versions
    ]

@router.post("", response_model=ScenarioResponse)
def create_scenario(scenario: ScenarioCreate, db: Session = Depends(get_db)):
    """Creates a new scenario parameter set without altering baseline inventory."""
    version_tag = f"scen-{scenario.name.lower().replace(' ', '-')[:24]}"
    existing = db.query(DatasetVersion).filter(DatasetVersion.version_tag == version_tag).first()
    if existing:
        version_tag = f"{version_tag}-{int(datetime.utcnow().timestamp())}"

    ds = DatasetVersion(
        version_tag=version_tag,
        description=scenario.description or f"Scenario: {scenario.name}",
        is_active=True,
        random_seed=42,
        parameters={
            "demand_multiplier": scenario.demand_multiplier,
            "transport_cost_multiplier": scenario.transport_cost_multiplier,
            "shelf_life_reduction_days": scenario.shelf_life_reduction_days,
        },
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)

    return ScenarioResponse(
        id=ds.id,
        name=scenario.name,
        version_tag=ds.version_tag,
        description=ds.description,
        parameters=ds.parameters,
        is_active=ds.is_active,
    )
