# StockWise AI — Frontend Dashboard & Distribution Intelligence Guide

## 1. Overview and Architecture

StockWise AI features a local-first, responsive, supply-chain control-tower web dashboard built with **Next.js (App Router)**, **TypeScript**, **Tailwind CSS**, **TanStack React Query**, and **Recharts**.

The frontend interfaces directly with the local **FastAPI** backend, providing operational visibility across 4 regional warehouses, 16 FMCG product SKUs, and 50 retail destination corridors.

### Key Architectural Tenets
1. **Local-First & Zero External Telemetry**: Runs completely offline against the local FastAPI SQLite instance. No external maps, trackers, or cloud analytics are loaded.
2. **True Operational Data (No Hardcoded Mocking)**: Every metric, shipment schedule, forecast curve, and backtesting score is dynamically fetched from backend endpoints or rendered in an explicit typed empty/error state.
3. **Transparent Algorithm Limitations**: Prominently communicates simulation status and architectural gaps (GAP-1: store on-hand inventory assumed zero, GAP-2: in-transit commitments assumed zero).
4. **Independent Verification Display**: Explicitly displays verification status from the 12-invariant audit verifier; never disguises an infeasible solver run as a successful recommendation.

---

## 2. Implemented Modules and Pages

| Tab / Module | Description | Primary Endpoints |
| :--- | :--- | :--- |
| **Overview Dashboard** | Network scope (Hubs, Stores, SKUs), 4-tier inventory accounting (Physical on-hand, Reserved, Available, Usable), replenishment health, latest optimization run status, and warehouse storage chart. | `GET /api/v1/inventory/overview`<br>`POST /api/v1/replenishment/summary`<br>`GET /api/v1/planning/runs` |
| **Inventory Explorer** | Batch-level ledger table with warehouse, product, and batch status filters (`AVAILABLE`, `RESERVED`, `QUARANTINED`, `EXPIRED`), physical vs. usable accounting, and FEFO expiry badges. | `GET /api/v1/inventory/batches`<br>`GET /api/v1/inventory/warehouses`<br>`GET /api/v1/inventory/products` |
| **Demand Forecasting** | Corridor time-series selector (product &times; destination), algorithm picker (`naive`, `ewma`, `seasonal_naive`), horizon (7, 14, 30 days), interactive historical vs. forecast Recharts curve, and holdout backtest evaluation (MAE &amp; WAPE). | `POST /api/v1/forecast`<br>`POST /api/v1/forecast/evaluate`<br>`GET /api/v1/demand/history` |
| **Replenishment Planner** | Downstream replenishment requirements ledger displaying route lead times, LTD, safety stock (units &amp; formula), reorder thresholds, order quantities, risk tiers (`Critical`, `High`, `Moderate`, `Low`), and driver explanation drawer. | `POST /api/v1/replenishment/summary` |
| **Optimizer Planner** | Formulation controls for profile (`balanced`, `service_first`, `cost_first`), max lead time cutoffs, Cost-First fulfillment rate floors, solver status banners (`OPTIMAL`, `FEASIBLE`, `TARGET_UNACHIEVABLE`, `INFEASIBLE`), shipment schedule, unmet demand ledger, and verifier report. | `POST /api/v1/planning/run` |
| **Scenario Comparison** | Side-by-side comparative matrix evaluating Cost-First vs. Balanced vs. Service-First on identical inputs, with delta calculations (units and transport investment) and comparative freight charts. | `POST /api/v1/planning/run` |
| **Planning History** | Chronological audit log of all persisted optimization runs with one-click detail inspector, full shipment schedules, and CSV export. | `GET /api/v1/planning/runs`<br>`GET /api/v1/planning/runs/{run_code}` |

---

## 3. Environment Variables & Configuration

The web client communicates with the backend via `apps/web/lib/api.ts`.

| Variable | Description | Default |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | Base URL of the running FastAPI server | `http://localhost:8000` |

---

## 4. How to Run Locally

### 1. Start Backend API
```bash
# From workspace root
.venv\Scripts\python.exe -m uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Check health: `http://127.0.0.1:8000/api/v1/health`

### 2. Start Frontend Dev Server
```bash
cd apps/web
npm run dev
```
Open browser at: `http://localhost:3000`

### 3. Run Production Build & Verification
```bash
cd apps/web
npx tsc --noEmit     # TypeScript type-checking
npm test             # Vitest unit test suite (18 tests)
npm run build        # Optimized static production build
```

---

## 5. Workflow Guides

### Executing an Optimization Run
1. Navigate to **Optimizer Planner** via top navigation.
2. Select your optimization profile:
   - **Balanced** (Default): Minimizes transport cost + transit freshness penalty ($0.20/day/unit) + lost sales penalty.
   - **Service-First**: Two-stage lexicographic solver. Minimizes unmet demand to the absolute global limit, then minimizes freight without dropping a single unit.
   - **Cost-First**: Minimizes freight cost subject to a configurable network fulfillment rate floor (default &ge; 80%).
3. Adjust planning horizon (7, 14, 30 days) and optional lead time cutoff (e.g. 3.0 days).
4. Click **Run Local Optimizer**. The solver executes asynchronously, displaying solver runtime, feasibility status, and returned shipment schedules.

### Comparing Optimization Profiles
1. Navigate to **Scenario Compare**.
2. Select the target horizon (e.g. 7 days) and minimum fulfillment floor.
3. Click **Run Scenario Comparison**.
4. The system executes all 3 formulations against identical network corridors, displaying exact units shipped, freight cost deltas, and average cost per unit.

### Exporting Planning Results to CSV
1. When viewing a plan in the **Optimizer Planner** or inspecting a prior run in **Planning History**, click **Export CSV**.
2. The browser generates `stockwise_shipments_{run_code}.csv` with standard RFC 4180 escaping, metadata headers, and the required advisory disclaimer.

---

## 6. Known Model Limitations & Simulated Data Disclosures

* **Simulated Demand Stream**: Historical daily demand across 800 corridors is deterministically generated using day-of-week seasonality, Poisson daily orders, and normal lead times.
* **GAP-1 (Store On-Hand Inventory = 0)**: Store-level physical inventory is currently not modeled in the schema and is treated as zero.
* **GAP-2 (In-Transit Dispatches = 0)**: Committed dispatches currently in transit are not tracked and treated as zero. Consequently, gross replenishment equals the full reorder threshold (LTD + Safety Stock).
* **Advisory Plan Disclaimer**: Generating an optimization run produces planning recommendations. It does not deduct or dispatch physical inventory from warehouse batches.
