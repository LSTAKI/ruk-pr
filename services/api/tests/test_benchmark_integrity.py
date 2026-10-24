"""
Test Benchmark Integrity & Independent Mathematical Audit (Prompt 9)
=====================================================================

Validates:
1. Dataset entity integrity and record counts (4 WH, 16 Prod, 50 Dest, 200 Route, 158 Batch, 96k Demand).
2. Exact replenishment demand reconciliation across 800 corridors (39,878 integer units).
3. Exact empirical benchmark outputs for Cost-First, Service-First, Balanced, and Greedy Baseline.
4. Independent 12-invariant verification compliance on all solver profiles.
5. Strict equality: Fulfilled + Unmet == Total Demanded.
"""

import pytest
from app.db.session import SessionLocal
from app.db.models import (
    DatasetVersion,
    Warehouse,
    Product,
    Destination,
    InventoryItem,
    Route,
    DailyDemandHistory,
)
from app.schemas.plan import PlanRequest, OptimizationParameters
from app.routes.planning import execute_planning_run


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_dataset_record_counts(db_session):
    """Verifies that the active database contains exact deterministic FMCG counts."""
    assert db_session.query(Warehouse).count() == 4
    assert db_session.query(Product).count() == 16
    assert db_session.query(Destination).count() == 50
    assert db_session.query(Route).count() == 200
    assert db_session.query(InventoryItem).count() == 158
    assert db_session.query(DailyDemandHistory).count() == 96000

    # Verify 800 distinct product-destination pairs with 120 days each
    corridor_counts = (
        db_session.query(
            DailyDemandHistory.destination_id,
            DailyDemandHistory.product_id,
        )
        .distinct()
        .count()
    )
    assert corridor_counts == 800


def test_benchmark_mathematical_reconciliation(db_session):
    """Verifies empirical benchmark figures, demand reconciliation, and baseline comparison."""
    # 1. Cost-First Profile
    cost_req = PlanRequest(
        forecast_horizon_days=7,
        optimization_profile="cost_first",
        min_fulfillment_rate=0.80,
        parameters=OptimizationParameters(
            profile="cost_first",
            min_fulfillment_rate=0.80,
            use_replenishment_engine=True,
            lead_time_penalty_weight=0.20,
        ),
    )
    cost_res = execute_planning_run(cost_req, db=db_session)
    assert cost_res.solver_status == "OPTIMAL"
    assert cost_res.verification.is_feasible is True
    assert cost_res.metrics.total_demanded_units == 39878
    assert cost_res.metrics.total_shipped_units == 35963
    assert cost_res.metrics.total_unmet_units == 3915
    assert cost_res.metrics.total_shipped_units + cost_res.metrics.total_unmet_units == 39878
    assert round(cost_res.metrics.fulfillment_rate, 4) == 0.9018
    assert round(cost_res.metrics.total_transport_cost, 2) == 50150.99
    assert round(cost_res.metrics.total_transport_cost / 35963, 4) == 1.3945

    # 2. Service-First Profile
    service_req = PlanRequest(
        forecast_horizon_days=7,
        optimization_profile="service_first",
        parameters=OptimizationParameters(
            profile="service_first",
            use_replenishment_engine=True,
            lead_time_penalty_weight=0.20,
        ),
    )
    service_res = execute_planning_run(service_req, db=db_session)
    assert service_res.solver_status == "OPTIMAL"
    assert service_res.verification.is_feasible is True
    assert service_res.metrics.total_demanded_units == 39878
    assert service_res.metrics.total_shipped_units == 36583
    assert service_res.metrics.total_unmet_units == 3295
    assert service_res.metrics.total_shipped_units + service_res.metrics.total_unmet_units == 39878
    assert round(service_res.metrics.fulfillment_rate, 4) == 0.9174
    assert round(service_res.metrics.total_transport_cost, 2) == 52812.09
    assert round(service_res.metrics.total_transport_cost / 36583, 4) == 1.4436

    # 3. Balanced Profile
    balanced_req = PlanRequest(
        forecast_horizon_days=7,
        optimization_profile="balanced",
        parameters=OptimizationParameters(
            profile="balanced",
            use_replenishment_engine=True,
            lead_time_penalty_weight=0.20,
        ),
    )
    balanced_res = execute_planning_run(balanced_req, db=db_session)
    assert balanced_res.solver_status == "OPTIMAL"
    assert balanced_res.verification.is_feasible is True
    assert balanced_res.metrics.total_demanded_units == 39878
    assert balanced_res.metrics.total_shipped_units == 36583
    assert balanced_res.metrics.total_unmet_units == 3295
    assert round(balanced_res.metrics.fulfillment_rate, 4) == 0.9174
    assert round(balanced_res.metrics.total_transport_cost, 2) == 52816.51
    assert round(balanced_res.metrics.total_transport_cost / 36583, 4) == 1.4437

    # 4. Greedy Baseline Evaluation
    bc = service_res.baseline_comparison
    assert bc is not None
    assert bc.baseline_total_units == 36583
    assert round(bc.baseline_total_cost, 2) == 54085.66
    assert round(bc.baseline_fulfillment_rate, 4) == 0.9174
    assert round(bc.baseline_total_cost / 36583, 4) == 1.4784

    # 5. Service-First Savings vs Greedy Baseline
    freight_diff = bc.baseline_total_cost - service_res.metrics.total_transport_cost
    pct_reduction = (freight_diff / bc.baseline_total_cost) * 100.0
    assert round(freight_diff, 2) == 1273.57
    assert round(pct_reduction, 2) == 2.35
