"""
StockWise AI - FastAPI Application Entrypoint
FMCG Distribution Intelligence & Inventory Optimization Engine
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes.health import router as health_router
from app.routes.inventory import router as inventory_router
from app.routes.planning import router as planning_router
from app.routes.scenarios import router as scenarios_router
from app.routes.routes import router as routes_router
from app.routes.demand import router as demand_router
from app.db.session import engine, Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables are created for local development
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="StockWise AI Engine",
    description="FMCG Distribution Intelligence & Inventory Optimization Engine API",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration
app.include_router(health_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(planning_router, prefix="/api/v1")
app.include_router(scenarios_router, prefix="/api/v1")
app.include_router(routes_router, prefix="/api/v1")
app.include_router(demand_router, prefix="/api/v1")

# Top-level health check endpoint for container probes
@app.get("/health")
def root_health():
    return {"status": "ok", "service": "StockWise AI", "version": "0.2.0"}
