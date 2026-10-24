"""Common API schemas."""

from typing import Optional, Any, Dict
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    environment: str
    database_connected: bool
    version: str = "0.1.0"
    active_dataset_version: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    details: Optional[Dict[str, Any]] = None
