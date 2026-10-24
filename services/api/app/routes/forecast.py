"""Demand Forecasting API route handlers."""

from collections import defaultdict
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import DailyDemandHistory, Destination, Product
from app.engine.forecast.data_prep import prepare_demand_series
from app.engine.forecast.methods import (
    SUPPORTED_HORIZONS,
    SUPPORTED_METHODS,
    forecast,
)
from app.engine.forecast.evaluation import (
    SeriesEvaluation,
    aggregate_evaluations,
    evaluate_series,
)
from app.schemas.forecast import (
    AggregateMethodSummary,
    DailyForecastValue,
    ForecastEvaluationRequest,
    ForecastEvaluationResponse,
    ForecastRequest,
    ForecastResponse,
    MethodEvalResult,
    SeriesEvalResult,
)

router = APIRouter(prefix="/forecast", tags=["Forecast"])

# ---------------------------------------------------------------------------
# POST /api/v1/forecast  — single product-destination forecast
# ---------------------------------------------------------------------------

@router.post("", response_model=ForecastResponse, status_code=200)
def generate_forecast(request: ForecastRequest, db: Session = Depends(get_db)):
    """Generates a demand forecast for a specific product-destination combination.

    Returns daily forecast values, total expected demand, the method used,
    and any data-quality warnings.

    Error cases:
      - 404 if product_id or destination_id does not exist.
      - 422 if horizon_days, method, or ewma_alpha are invalid (validated by Pydantic).
      - 200 with method_available=False if history is insufficient.
    """
    # Validate entities exist
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={request.product_id} not found.",
        )

    destination = db.query(Destination).filter(
        Destination.id == request.destination_id
    ).first()
    if not destination:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination with id={request.destination_id} not found.",
        )

    # Targeted DB query — only fetch rows for this (product, destination) pair
    rows = (
        db.query(DailyDemandHistory)
        .filter(
            DailyDemandHistory.product_id == request.product_id,
            DailyDemandHistory.destination_id == request.destination_id,
        )
        .order_by(DailyDemandHistory.demand_date.asc())
        .all()
    )

    raw_records = [
        {
            "demand_date": r.demand_date,
            "quantity_demanded": r.quantity_demanded,
            "quantity_sold": r.quantity_sold,
            "is_simulated": r.is_simulated,
        }
        for r in rows
    ]

    as_of = request.as_of_date

    series = prepare_demand_series(raw_records, as_of_date=as_of)

    result = forecast(
        series,
        method=request.method,
        horizon_days=request.horizon_days,
        forecast_origin=series.records[-1].demand_date if series.records else as_of,
        ewma_alpha=request.ewma_alpha,
    )

    daily_forecasts = [
        DailyForecastValue(date=df["date"], value=df["value"])
        for df in result.daily_forecasts
    ]

    forecasted_units = max(0, round(result.total_demand))

    return ForecastResponse(
        product_id=request.product_id,
        product_sku=product.sku,
        destination_id=request.destination_id,
        destination_code=destination.code,
        generated_at=datetime.utcnow(),
        horizon_days=request.horizon_days,
        method=result.method,
        method_available=result.method_available,
        unavailability_reason=result.unavailability_reason,
        daily_forecasts=daily_forecasts,
        total_demand=result.total_demand,
        daily_mean_demand=result.daily_mean_demand,
        forecasted_units=forecasted_units,
        history_observations_used=result.history_observations_used,
        warnings=result.warnings,
        is_simulated_data=series.is_simulated,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/forecast/methods  — list supported methods and horizons
# ---------------------------------------------------------------------------

@router.get("/methods")
def list_forecast_methods():
    """Returns the list of supported forecasting methods and horizons."""
    return {
        "supported_methods": list(SUPPORTED_METHODS),
        "supported_horizons": list(SUPPORTED_HORIZONS),
        "method_descriptions": {
            "naive": (
                "Naïve baseline: ŷ(t+h) = y(T) for all h. "
                "Uses most recent observation. Requires ≥ 1 historical record."
            ),
            "ewma": (
                "Exponentially Weighted Moving Average: s(T) projected flat. "
                "Configurable alpha ∈ (0,1]. Requires ≥ 7 historical records."
            ),
            "seasonal_naive": (
                "Weekly seasonal-naïve: ŷ(t+h) = y(T − (7 − (h−1) mod 7)). "
                "Requires ≥ 14 historical records (two full weeks)."
            ),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/v1/forecast/evaluate  — backtesting evaluation
# ---------------------------------------------------------------------------

@router.post("/evaluate", response_model=ForecastEvaluationResponse, status_code=200)
def evaluate_forecast_accuracy(
    request: ForecastEvaluationRequest,
    db: Session = Depends(get_db),
):
    """Runs historical backtesting on demand data using chronological train/test split.

    Evaluates all three forecasting methods (naive, ewma, seasonal_naive) and
    returns MAE and WAPE per method, per series and in aggregate.

    Parameters (via request body)
    --------
    product_id:
        Optional filter to evaluate only one product.
    destination_id:
        Optional filter to evaluate only one destination.
    ewma_alpha:
        EWMA smoothing parameter for evaluation.
    test_fraction:
        Fraction of data reserved for the holdout test partition (default 0.2).
    min_test_days:
        Minimum test observations (default 7).

    Error cases:
      - 404 if a specified product_id or destination_id does not exist.
      - 400 if no demand history is found for the specified filters.
    """
    # Validate entity existence when IDs are explicitly provided
    if request.product_id is not None:
        if not db.query(Product).filter(Product.id == request.product_id).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id={request.product_id} not found.",
            )
    if request.destination_id is not None:
        if not db.query(Destination).filter(
            Destination.id == request.destination_id
        ).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination with id={request.destination_id} not found.",
            )

    # Single batch query — avoids N×M individual queries
    query = db.query(
        DailyDemandHistory,
        Destination.code.label("dest_code"),
        Product.sku.label("prod_sku"),
    ).join(
        Destination, DailyDemandHistory.destination_id == Destination.id
    ).join(
        Product, DailyDemandHistory.product_id == Product.id
    )

    if request.product_id is not None:
        query = query.filter(DailyDemandHistory.product_id == request.product_id)
    if request.destination_id is not None:
        query = query.filter(DailyDemandHistory.destination_id == request.destination_id)

    all_records = query.order_by(DailyDemandHistory.demand_date.asc()).all()

    if not all_records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No demand history found for the specified filters.",
        )

    # Group by (destination_id, product_id)
    grouped: dict = defaultdict(list)
    meta: dict = {}   # (dst_id, prod_id) → (dst_code, prod_sku)

    for row, dest_code, prod_sku in all_records:
        key = (row.destination_id, row.product_id)
        grouped[key].append({
            "demand_date": row.demand_date,
            "quantity_demanded": row.quantity_demanded,
            "quantity_sold": row.quantity_sold,
            "is_simulated": row.is_simulated,
        })
        meta[key] = (dest_code, prod_sku)

    as_of = request.as_of_date

    series_results: List[SeriesEvaluation] = []
    for (dst_id, prod_id), rows in grouped.items():
        dest_code, prod_sku = meta[(dst_id, prod_id)]
        series = prepare_demand_series(rows, as_of_date=as_of)
        ev = evaluate_series(
            series,
            ewma_alpha=request.ewma_alpha,
            test_fraction=request.test_fraction,
            min_test_days=request.min_test_days,
            product_id=prod_id,
            destination_id=dst_id,
            product_sku=prod_sku,
            destination_code=dest_code,
        )
        series_results.append(ev)

    agg = aggregate_evaluations(series_results)

    # Build response
    agg_method_schemas = {}
    for method_name, stats in agg.methods.items():
        agg_method_schemas[method_name] = AggregateMethodSummary(
            method=method_name,
            series_with_method=stats["series_with_method"],
            mae_mean=stats["mae_mean"],
            mae_min=stats["mae_min"],
            mae_max=stats["mae_max"],
            wape_mean_pct=stats["wape_mean_pct"],
            wape_min_pct=stats["wape_min_pct"],
            wape_max_pct=stats["wape_max_pct"],
            wape_series_with_zero_actuals=stats["wape_series_with_zero_actuals"],
        )

    series_schemas = []
    for sr in series_results:
        method_schemas = {}
        for mn, me in sr.methods.items():
            method_schemas[mn] = MethodEvalResult(
                method=mn,
                method_available=me.method_available,
                unavailability_reason=me.unavailability_reason,
                mae=me.mae,
                wape_pct=me.wape,
                wape_unavailable_reason=me.wape_unavailable_reason,
                n_evaluated=me.n_evaluated,
                evaluation_start=me.evaluation_start,
                evaluation_end=me.evaluation_end,
            )
        series_schemas.append(
            SeriesEvalResult(
                product_id=sr.product_id,
                destination_id=sr.destination_id,
                product_sku=sr.product_sku,
                destination_code=sr.destination_code,
                train_observations=sr.train_observations,
                test_observations=sr.test_observations,
                total_observations=sr.total_observations,
                evaluation_start=sr.evaluation_start,
                evaluation_end=sr.evaluation_end,
                methods=method_schemas,
                warnings=sr.warnings,
            )
        )

    return ForecastEvaluationResponse(
        n_series_evaluated=agg.n_series_evaluated,
        total_observations_evaluated=agg.total_observations_evaluated,
        aggregate=agg_method_schemas,
        caveats=agg.caveats,
        series=series_schemas,
    )
