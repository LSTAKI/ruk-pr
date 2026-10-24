"""Scenario simulation request and response schemas."""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=128)
    description: Optional[str] = None
    demand_multiplier: float = Field(default=1.0, ge=0.1, le=5.0)
    transport_cost_multiplier: float = Field(default=1.0, ge=0.5, le=5.0)
    shelf_life_reduction_days: int = Field(default=0, ge=0, le=90)
    base_dataset_version_id: Optional[int] = None

class ScenarioResponse(BaseModel):
    id: int
    name: str
    version_tag: str
    description: Optional[str]
    parameters: Dict[str, Any]
    is_active: bool
