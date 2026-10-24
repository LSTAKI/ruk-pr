"""Routes package."""
from app.routes.health import router as health_router
from app.routes.inventory import router as inventory_router
from app.routes.planning import router as planning_router
from app.routes.scenarios import router as scenarios_router
from app.routes.routes import router as routes_router
from app.routes.demand import router as demand_router

__all__ = [
    "health_router",
    "inventory_router",
    "planning_router",
    "scenarios_router",
    "routes_router",
    "demand_router",
]
