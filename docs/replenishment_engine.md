# StockWise AI — Inventory Position, Safety Stock & Replenishment Engine

## Overview

The Inventory Position, Safety Stock & Replenishment Engine bridges historical demand forecasts with distribution planning. It determines:
* **How much stock is physically usable** at each warehouse (enforcing batch-level expiry, quarantine, and reservations).
* **How much buffer stock is required** for each product-destination pair to hedge against demand variability during delivery lead times.
* **How many units must be shipped** to avoid stockouts while minimizing holding and transport costs.
* **Which retail destinations face imminent stockout risk** categorized by clear, objective criteria.
* **A structured contract for the OR-Tools optimization engine**, separating demand replenishment signals from warehouse supply constraints.

All computations are deterministic, fully explainable, and verified against 149 backend tests with hand-calculated benchmark cases.

---

## 1. Inventory Accounting Definitions

Accurate replenishment depends on strict inventory accounting. The engine enforces the following invariants:

| Category | Definition | Usable for Replenishment? | Accounting Rules |
|----------|------------|---------------------------|------------------|
| **Total On-Hand** | Total units physically present in warehouse bins across all batches. | No (raw quantity only) | $\sum_{\text{batches}} \text{quantity}$ |
| **Available / Usable** | Units in active batches that are unreserved, non-expired, and non-quarantined. | **Yes** | $\max(0, \text{usable\_batches} - \text{reserved})$ |
| **Reserved** | Units allocated to pending customer orders or dispatch instructions. | **No** | Never double-allocated or counted in usable stock. |
| **Expired** | Batches where `expiry_date <= as_of_date`. | **No** | Excluded completely; flagged for disposal. |
| **Quarantined / Damaged** | Batches with status `quarantine` or `damaged` regardless of expiry date. | **No** | Excluded from available inventory. |

### Warehouse vs. Destination Inventory Separation (GAP-1)
* **Warehouse stock** represents centralized regional distribution center inventory.
* **Destination stock** represents store-level or local retail node on-hand inventory.
* **Strict invariant:** Warehouse stock and destination stock are **never summed**. In the current schema, warehouse stock is tracked via `inventory_batches`. 
* **Database GAP-1:** The current database does not track local store-level inventory (`DestinationInventory` table). Until implemented, store-level on-hand is assumed to be $0$ and warning `destination_inventory_not_tracked_assumed_zero` is emitted.

---

## 2. Safety Stock Methodology

### Classical Square-Root Formula
The baseline safety stock buffer is calculated as:
$$SS = z \cdot \sigma_d \cdot \sqrt{L}$$

Where:
* **$z$**: Service level factor (z-score from standard normal distribution).
  * $85\% \to z \approx 1.04$
  * $90\% \to z \approx 1.28$
  * $95\% \to z \approx 1.65$ (default)
  * $99\% \to z \approx 2.33$
  * *Important:* $z$ is a configuration factor, **not a guaranteed achieved service level**.
* **$\sigma_d$**: Sample standard deviation of daily demand with Bessel correction ($ddof=1$):
  $$\sigma_d = \sqrt{\frac{1}{N-1} \sum_{i=1}^N (d_i - \bar{d})^2}$$
* **$L$**: Supplier replenishment lead time in days (supports fractional lead times, e.g., $1.5$ days, without arbitrary integer rounding).

### Statistical Assumptions & FMCG Caveats
1. **i.i.d. Demand:** Daily demand is assumed to be independent and identically distributed. (In FMCG, weekend demand peaks violate independence; seasonal adjustments are captured via the forecasting layer).
2. **Normal Distribution:** Demand errors are assumed symmetric and normally distributed. (Low-velocity or intermittent items violate this assumption).
3. **Deterministic Lead Time:** Lead time $L$ is assumed constant. Lead time variance is not modeled in this release.

### Fallback Policy
When $\sigma_d$ cannot be calculated (fewer than $7$ historical observations, or zero demand variance):
$$SS_{\text{fallback}} = \text{fallback\_factor} \cdot \bar{d} \cdot L$$
* Default `fallback_factor = 0.25` (25% buffer of lead-time demand).
* When fallback is invoked, `safety_stock_fallback_used` warning code is explicitly emitted.

### Buffer Separation (No Double-Counting)
* Safety stock is a **threshold buffer target**, never a physical asset.
* Safety stock is **never added to on-hand inventory** and **never added directly to forecasted demand**.
* It is strictly used in threshold calculation: $\text{Threshold} = \text{Lead Time Demand} + \text{Safety Stock}$.

---

## 3. Lead-Time Demand Calculation

Lead-time demand ($LTD$) represents anticipated sales during the transit interval:
$$LTD = \bar{d} \cdot L$$

* **$\bar{d}$**: Daily demand estimate supplied by the Demand Forecasting Engine (EWMA default with $\alpha = 0.3$, Naive, or Seasonal-Naive).
* **$L$**: Transport lead time in days from the active route table.
* **Fractional Lead Times:** For $L = 1.5$ days and $\bar{d} = 20.0$ units/day, $LTD = 30.0$ units (exact multiplication; no truncation).

---

## 4. Replenishment Calculation Formulas

Given:
* $LTD$: Lead-time demand
* $SS$: Safety stock units ($z \cdot \sigma_d \cdot \sqrt{L}$)
* $P$: Projected inventory position ($\text{Usable Stock at Destination} + \text{Incoming Committed Stock}$)

### Core Formulas:
1. **Replenishment Threshold ($T$):**
   $$T = LTD + SS$$
2. **Gross Replenishment Requirement:**
   $$\text{Gross} = \max(0, T - P)$$
3. **Recommended Replenishment Quantity ($\text{Units}$):**
   $$\text{Replenishment Qty} = \lceil \text{Gross} \rceil$$
   *(Guaranteed non-negative integer via ceiling rounding).*

---

## 5. Stockout Risk Classification Rules

The engine assigns risk categories based on **Cover Days**:
$$\text{Cover Days} = \begin{cases} \frac{P}{\bar{d}} & \text{if } \bar{d} > 0 \\ 0 & \text{otherwise} \end{cases}$$

$$\text{Safety Stock Days} = \begin{cases} \frac{SS}{\bar{d}} & \text{if } \bar{d} > 0 \\ 0 & \text{otherwise} \end{cases}$$

| Risk Category | Criteria | Operational Meaning |
|---------------|----------|---------------------|
| **Critical** | $\text{Cover Days} = 0$ | Destination is already stocked out; emergency delivery required. |
| **High** | $0 < \text{Cover Days} \le L$ | Destination will stock out before standard shipment arrives. |
| **Moderate** | $L < \text{Cover Days} \le L + \text{Safety Stock Days}$ | Stock is below replenishment threshold; order should be scheduled. |
| **Low** | $\text{Cover Days} > L + \text{Safety Stock Days}$ | Stock is healthy and above threshold; no immediate replenishment needed. |
| **InsufficientData** | $\bar{d} = 0$ or history missing | Inadequate data to determine risk reliably. |

> **Transparency Note:** These risk categories are **heuristic classification bands**, not mathematically calibrated Bayesian stockout probabilities. They provide operational transparency without misleading planners.

---

## 6. Route Selection Policy

When multiple active routes connect candidate warehouses to a destination:
1. **Primary Sort:** Minimum transit lead time $L$ (fastest delivery to prevent stockout).
2. **Secondary Sort (Tie-breaker):** Minimum unit transport cost ($\$/\text{unit}$).
3. **Route Selection Reason:** The engine outputs a reason code (e.g., `fastest_delivery_min_lead_time_2.0_days`) detailing why the route was chosen for threshold baseline.

---

## 7. Known System Limitations & Database Gaps

* **GAP-1 (Destination Inventory):** The current schema tracks regional warehouse inventory via `inventory_batches`, but lacks a store-level `destination_inventory` table. Destination on-hand is reported as $0$ with warning `WARN_NO_DESTINATION_INVENTORY`.
* **GAP-2 (In-Transit / Confirmed Dispatch):** The schema records recommended shipments (`shipment_recommendations`), but not confirmed in-transit dispatches. In-transit incoming stock is reported as $0$ with warning `WARN_NO_INCOMING_SHIPMENTS`.
* **Deterministic Simulation:** All default test/demo records originate from deterministic FMCG simulation fixtures.

---

## 8. Hand-Calculated Reference Benchmarks

These reference cases can be independently verified by hand:

### Example 1: Standard Replenishment Case
* Daily mean demand $\bar{d} = 10.0$ units/day
* Sample standard deviation $\sigma_d = 2.0$ units/day
* Route lead time $L = 4.0$ days ($\sqrt{L} = 2.0$)
* Service level $z = 1.65$
* Projected destination stock $P = 15.0$ units

**Calculations:**
* $LTD = 10.0 \times 4.0 = 40.0$ units
* $SS = 1.65 \times 2.0 \times 2.0 = 6.60$ units
* Threshold $T = 40.0 + 6.60 = 46.60$ units
* Gross requirement $= 46.60 - 15.0 = 31.60$ units
* Replenishment quantity $= \lceil 31.60 \rceil = 32$ units
* Cover days $= 15.0 / 10.0 = 1.5$ days
* Since $0 < 1.5 \le 4.0$, **Risk Category = High**.

### Example 2: Fractional Lead Time Case
* Daily mean demand $\bar{d} = 20.0$ units/day
* $\sigma_d = 3.0$ units/day
* Route lead time $L = 1.5$ days ($\sqrt{1.5} \approx 1.22474$)
* Service level $z = 1.65$
* Projected destination stock $P = 0$ units

**Calculations:**
* $LTD = 20.0 \times 1.5 = 30.0$ units
* $SS = 1.65 \times 3.0 \times 1.22474487 \approx 6.0625$ units
* Threshold $T = 30.0 + 6.0625 = 36.0625$ units
* Gross requirement $= 36.0625 - 0 = 36.0625$ units
* Replenishment quantity $= \lceil 36.0625 \rceil = 37$ units
* Cover days $= 0$, **Risk Category = Critical**.

---

## 9. API Reference

### 1. `POST /api/v1/replenishment`
Calculates replenishment for a specific product and destination across all active warehouse routes.

**Request Body:**
```json
{
  "product_id": 1,
  "destination_id": 1,
  "forecast_method": "ewma",
  "ewma_alpha": 0.3,
  "safety_stock_config": {
    "service_level_z": 1.65,
    "fallback_factor": 0.25,
    "min_safety_stock_units": 0
  }
}
```

### 2. `POST /api/v1/replenishment/summary`
Batch calculation across multiple product-destination pairs with pagination and risk filtering.

**Query Parameters:**
* `limit`: Default `50`, Max `500`
* `offset`: Pagination offset
* `risk_filter`: Filter by minimum risk (`Critical`, `High`, `Moderate`)

### 3. `GET /api/v1/replenishment/optimizer-contract`
Provides a clean, typed payload conforming to the OR-Tools optimization engine contract.

### 4. `GET /api/v1/replenishment/risk-rules`
Self-documenting endpoint exposing the heuristic risk rules, formulas, and active data caveats.

---

## 10. Test Verification Results

The entire backend test suite was run against Python 3.11 with SQLite:
* **Total Tests Executed:** 149
* **Passed:** 149
* **Failed:** 0
* **Test Suite Modules:**
  * `test_replenishment_engine.py` (62 tests): Acceptance criteria 1-19, hand calculations, fallback policies, route selection, and schema contracts.
  * `test_forecasting_engine.py` (68 tests): Naive, EWMA, Seasonal-Naive, WAPE/MAE evaluation.
  * `test_position.py` (9 tests): Batch accounting, expiry exclusion, reserved stock protections.
  * `test_api.py` (10 tests): Core endpoint sanity, health check, scenario planning.
