# StockWise AI — Demand Forecasting Engine

## Overview

The forecasting engine converts historical product-destination demand records into deterministic, explainable forecasts that drive inventory replenishment and distribution optimization.

All forecasts are computed from real historical observations stored in the `daily_demand_history` table. No LLM, cloud API, or paid service is used. Results are identical for identical inputs.

---

## Forecasting Methods

### A. Naïve Baseline (`naive`)

**Mathematical definition:**
```
ŷ(t+h) = y(T)   for all h = 1, 2, …, H
```
where `T` is the index of the most recent observation.

**Behaviour:** Replicates the last observed demand value across the entire horizon.

**Minimum history required:** 1 observation.

**When to use:** Best as a benchmark or when very little history exists.

---

### B. EWMA — Exponentially Weighted Moving Average (`ewma`)

**Mathematical definition:**
```
s(1) = y(1)
s(t) = α · y(t) + (1 − α) · s(t−1)   for t = 2, 3, …, T
ŷ(t+h) = s(T)   for all h = 1, 2, …, H
```

**Smoothing parameter `α` ∈ (0, 1]:**

| α value | Effect |
|---------|--------|
| 0.1 – 0.2 | Heavy smoothing; forecast tracks long-term average |
| **0.3 (default)** | **Moderate; balances trend and noise for stable FMCG products** |
| 0.5 – 0.7 | Responsive; reacts quickly to recent demand changes |
| 0.9 – 1.0 | Naïve-like; almost purely driven by the most recent value |

**Minimum history required:** 7 observations.

**When to use:** Default method. Suitable for FMCG products with stable or slowly trending demand.

---

### C. Weekly Seasonal-Naïve (`seasonal_naive`)

**Mathematical definition:**
```
ŷ(t+h) = y(T − (7 − ((h−1) mod 7)))
```
Each forecast day uses the demand observed on the same weekday from the immediately preceding week.

**Behaviour:** Captures weekly seasonality (e.g., snack demand higher on weekends; dairy demand higher mid-week).

**Minimum history required:** 14 observations (two full 7-day cycles).

**When to use:** When a strong weekly pattern is known to exist. Check actual WAPE against naïve/EWMA before promoting to production.

---

## Configuration Parameters

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `method` | string | `naive`, `ewma`, `seasonal_naive` | `ewma` | Forecasting method |
| `horizon_days` | int | `7`, `14`, `30` | `7` | Forecast horizon |
| `ewma_alpha` | float | (0.0, 1.0] | `0.3` | EWMA smoothing factor |
| `as_of_date` | ISO 8601 date | any past date | today (UTC) | Forecast origin; future observations excluded |

---

## Missing-Data Policy

| Situation | Behaviour |
|-----------|-----------|
| **Gap in calendar dates** (missing record for a date within the series range) | Detected and reported as a warning. **Not filled with zero by default.** Gap-fill must be explicitly requested via `fill_gaps_with_zero=True`. |
| **Zero-demand observations** (record present, qty = 0) | Preserved as meaningful signal (e.g., store closed, product unavailable). |
| **Negative demand** | Rejected and reported via `WARN_NEGATIVE_DEMAND`. Row is excluded from the series. |
| **Future observations** (date > as_of_date) | Excluded to prevent data leakage. Reported via `WARN_FUTURE_OBSERVATIONS_EXCLUDED`. |
| **Duplicate dates** | First occurrence kept; duplicates dropped. Reported via `WARN_DUPLICATE_DATES`. |
| **Insufficient history** | Method reports `method_available=False` with a clear explanation; zero forecast returned as fallback. |

> **Why we do not silently treat missing observations as zero:** A missing DB record may indicate a data pipeline failure rather than true zero demand. Imputing zeros would underestimate demand and cause under-stocking. Callers must explicitly opt in to gap filling.

---

## Rounding Policy

Forecast values are computed as `float` (2 decimal places) inside the forecasting layer to preserve precision across method composition.

**Integer rounding** (`round()`, Python banker's rounding) is applied at exactly two boundaries:
1. `forecasted_units` field in `ForecastResponse` — consumed by the optimizer.
2. `forecasted_units` key in `PlanningForecastDict` — consumed by `DistributionSolver`.

This separation ensures the forecasting layer remains continuous while the optimizer receives the integer unit counts it requires.

---

## Evaluation Methodology

### Protocol

1. Prepare the full history series for each (product, destination) pair.
2. Split **chronologically**: earlier observations → train, later → test (default: last 20% = test).
3. Fit each method on the **train partition only**.
4. Evaluate against the **test partition** (never seen during training).

This is equivalent to a single-origin holdout. Rolling-origin evaluation is documented as a future enhancement.

### Accuracy Metrics

**MAE (Mean Absolute Error)**
```
MAE = (1/N) · Σ |y_i − ŷ_i|
```
- Always defined when N ≥ 1.
- Expressed in the same units as demand (cases/units/etc.).

**WAPE (Weighted Absolute Percentage Error)**
```
WAPE = Σ |y_i − ŷ_i| / Σ y_i  × 100%
```
- Numerically stable when any individual `y_i = 0` (unlike MAPE).
- Returns `None` with an explanation when `Σ y_i = 0` (entire test period is zero-demand).

### Important Caveats

> ⚠️ All backtesting results in this repository are produced from **deterministically simulated** FMCG data, not real business observations. They must not be used to make production deployment decisions without validation against actual demand data.

> ⚠️ No method is declared superior based solely on backtesting results. Numeric metrics are reported; interpretation is left to the analyst.

---

## API Endpoints

### `POST /api/v1/forecast`

Generate a forecast for a single product-destination pair.

**Request body:**
```json
{
  "product_id": 1,
  "destination_id": 1,
  "horizon_days": 7,
  "method": "ewma",
  "ewma_alpha": 0.3,
  "as_of_date": "2026-10-24"
}
```

**Response (200):**
```json
{
  "product_id": 1,
  "product_sku": "SKU-0001",
  "destination_id": 1,
  "destination_code": "DST-001",
  "generated_at": "2026-10-24T16:30:00",
  "horizon_days": 7,
  "method": "ewma",
  "method_available": true,
  "daily_forecasts": [
    {"date": "2026-10-25", "value": 52.40},
    ...
  ],
  "total_demand": 366.8,
  "daily_mean_demand": 52.40,
  "forecasted_units": 367,
  "history_observations_used": 120,
  "warnings": ["simulated_data"],
  "is_simulated_data": true
}
```

**Error responses:**
- `404` — product_id or destination_id not found
- `422` — invalid `horizon_days`, `method`, or `ewma_alpha`
- `200` with `method_available: false` — insufficient history

---

### `GET /api/v1/forecast/methods`

Returns the list of supported methods, horizons, and descriptions.

---

### `POST /api/v1/forecast/evaluate`

Runs chronological backtesting evaluation.

**Request body:**
```json
{
  "product_id": 1,
  "destination_id": 1,
  "ewma_alpha": 0.3,
  "test_fraction": 0.2,
  "min_test_days": 7
}
```

**Response includes:**
- Aggregate MAE and WAPE per method
- Per-series breakdown
- Evaluation period dates
- Caveats

**Error responses:**
- `404` — product_id or destination_id not found
- `400` — no demand history found

---

## Running Tests

```bash
# Run the full backend test suite
cd services/api
../.venv/Scripts/python.exe -m pytest tests/ -v

# Run only forecasting tests
../.venv/Scripts/python.exe -m pytest tests/test_forecasting_engine.py -v

# Run with coverage
../.venv/Scripts/python.exe -m pytest tests/test_forecasting_engine.py --tb=short -q
```

---

## Actual Test Results (2026-10-24)

```
============================= 95 passed in 4.09s ==============================
```

| Test group | Tests | Result |
|------------|-------|--------|
| Data preparation | 9 | ✅ All passed |
| Naïve forecast | 9 | ✅ All passed |
| EWMA forecast | 9 | ✅ All passed |
| Seasonal-naïve | 4 | ✅ All passed |
| Dispatch routing | 4 | ✅ All passed |
| Metrics (MAE/WAPE) | 7 | ✅ All passed |
| Backtesting | 8 | ✅ All passed |
| Position interface | 6 | ✅ All passed |
| Backward compat | 2 | ✅ All passed |
| API validation | 9 | ✅ All passed |
| Pre-existing tests | 28 | ✅ All passed |
| **Total** | **95** | **✅ 0 failures** |

---

## Outstanding Limitations and Future Work

Before forecast-driven replenishment can be safely used in production:

| # | Item | Severity |
|---|------|----------|
| 1 | **Safety-stock calibration** — current forecasts are point estimates; no demand variance or service-level target is modelled. A `z × σ_d × √L` buffer should be added before the optimizer. | High |
| 2 | **Lead-time uncertainty** — lead times in the Route table are point estimates. Probabilistic lead times would improve buffer calculations. | Medium |
| 3 | **Backorder / lost-sales policy** — when supply < demand, the policy for partial fulfilment is undefined. | Medium |
| 4 | **Rolling-horizon optimization** — the optimizer solves a single static period. MPC-style rolling horizon needed for production. | Medium |
| 5 | **Real data validation** — all accuracy metrics are from simulated data. They cannot be used as evidence of real-world forecast performance. | Critical |
| 6 | **Trend detection** — EWMA projects a flat level; if demand has a clear upward or downward trend, a Holt-Winters or linear trend model would improve accuracy. | Low |

---

*Generated: 2026-10-24. All metrics from simulated data only.*
