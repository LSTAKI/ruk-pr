# StockWise AI — Hackathon Demonstration & Business Validation Guide

> **Triwizathon Problem Statement 2**: AI-Powered FMCG Distribution Intelligence and Inventory Optimization Engine.  
> **Repository**: [https://github.com/LSTAKI/ruk-pr.git](https://github.com/LSTAKI/ruk-pr.git)  
> **Architecture**: Local-First, Next.js 15 App Router, FastAPI, SQLite3, Google OR-Tools MIP.

---

## A. Project Summary

Fast-Moving Consumer Goods (FMCG) distribution networks face a multi-variable operational dilemma every morning:
1. **Perishable Batches & Expiry (FEFO)**: Shipping products from distant hubs risks product expiration before customer purchase.
2. **Stockout Urgency**: Retail store shelves empty quickly under Poisson daily demand spikes.
3. **Logistics Cost Escalation**: Expedited deliveries and fragmented LTL shipments rapidly erode FMCG operating margins.

**StockWise AI** is an enterprise-grade distribution control tower that replaces heuristic guesswork and manual spreadsheets with:
* Deterministic time-series forecasting across 800 corridors (Naive, EWMA, Seasonal Naive) with chronological holdout backtesting.
* Dynamic multi-echelon safety stock and reorder thresholding.
* Constraint-aware Mixed-Integer Linear Programming (MIP) powered by Google OR-Tools.
* Multi-objective profile formulations: **Cost-First**, **Service-First**, and **Balanced**.
* An independent 12-invariant mathematical verification auditor.
* Driver-based natural language explanations for every shipment recommendation.

---

## B. System Architecture

```mermaid
graph TD
    A[SQLite3 DB / Master FMCG Data] --> B[FastAPI Engine]
    B --> C[Demand Forecaster: EWMA/Naive/Seasonal]
    C --> D[Replenishment Engine: Safety Stock & LTD]
    D --> E[Google OR-Tools MIP Solver]
    B --> F[Usable Inventory Accounting: FEFO]
    F --> E
    E --> G[Solution Verifier: 12 Invariants]
    E --> H[Decision Explainer: Driver Attribution]
    G --> I[Planning Run Record in SQLite]
    H --> I
    I --> J[Next.js 15 Control Tower Frontend]
    J --> K[CSV RFC 4180 / OWASP Sanitized Export]
```

### Module Responsibilities:
1. **Frontend (`apps/web`)**: Next.js 15 App Router with TanStack React Query v5, Recharts, and Tailwind CSS. Provides 7 interconnected control-tower tabs: Overview, Inventory Explorer, Demand Forecasting, Replenishment Planner, Optimizer Planner, Scenario Compare, and Planning History.
2. **Backend API (`services/api`)**: High-performance FastAPI server exposing typed Pydantic v2 schemas for inventory batches, demand history, forecasting, replenishment signals, planning runs, and scenario simulations.
3. **MIP Optimizer (`app.engine.optimize.optimizer`)**: Formulates the multi-commodity network flow problem with supply bounds, demand bounds, throughput limits, and lead-time cutoffs using Google OR-Tools.
4. **Independent Verifier (`app.engine.verify.verifier`)**: Validates 12 mathematical invariants (supply capacity, non-negativity, integer flow conservation, active route validity) completely outside the solver routine.
5. **Decision Explainer (`app.engine.explain.explainer`)**: Analyzes competing warehouse alternatives (freight rate differentials, transit lead times, stock availability) to produce human-readable planner justifications.

---

## C. Demo Setup & Local Startup

### 1. Prerequisites Check
Run the cross-platform environment verifier:
```bash
.venv\Scripts\python.exe scripts/verify_environment.py
```
*Expected: Python 3.11+, Node.js 18+, SQLite3 OK.*

### 2. Database Seeding (Seed: 42)
```bash
.venv\Scripts\python.exe scripts/seed_demo_data.py
```
*Expected: 4 warehouses, 16 products, 50 destinations, 200 routes, 158 inventory batches, and 96,000 demand history records seeded into `data/stockwise.db`.*

### 3. Launch Local Backend
In Terminal 1:
```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000 --reload
```
*Verify: Open `http://127.0.0.1:8000/api/v1/health` &rarr; `{"status": "ok", "database_connected": true}`.*

### 4. Launch Local Frontend
In Terminal 2:
```bash
cd apps/web
npm run dev
```
*Access: Open `http://localhost:3000` in Google Chrome or modern browser.*

---

## D. Step-by-Step Live Demonstration Script

| Step | Time | Navigation / Action | What to Highlight & Explain |
| :--- | :--- | :--- | :--- |
| **1. Application Shell & Health** | 0:00 - 0:30 | Open `http://localhost:3000` | Point out the **LOCAL-FIRST** badge, **Engine Online** indicator, and **Simulated FMCG v1.0** dataset tag. Emphasize zero external cloud dependencies. |
| **2. Inventory Accounting** | 0:30 - 1:00 | Click **Inventory Explorer** tab | Highlight the 4-tier accounting distinction: On-Hand vs. Reserved vs. Available vs. **Usable Stock**. Filter by `QUARANTINED` to prove that quarantined batches show **0 Usable units** and are excluded from allocation. |
| **3. Demand Forecasting** | 1:00 - 1:30 | Click **Demand Forecast** tab | Select Corridor `PRD-MILK` &rarr; `DST-001`. Select **EWMA** (&alpha; = 0.30) with a **7-day horizon**. Click **Generate Forecast**. Point out the Recharts curve showing historical demand actuals followed by forward projections. Click **Run Backtest Evaluation** to demonstrate holdout validation (MAE &amp; WAPE). |
| **4. Replenishment Risks** | 1:30 - 2:00 | Click **Replenishment** tab | Show the critical risk pairs and highlight the **Operational Model Notice (GAP-1 & GAP-2)** disclosing store-level inventory assumptions. Click **Details** on any row to open the mathematical driver explanation modal. |
| **5. OR-Tools Optimization** | 2:00 - 2:45 | Click **Optimizer Planner** tab | Select **Balanced** profile (7-day horizon). Click **Run Local Optimizer**. Point out the **OPTIMAL** status card, runtime (<0.5s), **Verifier: Feasible** badge, and shipment recommendation table. Expand a row to show the driver-based rationale explaining why alternatives were rejected. |
| **6. Scenario Trade-offs** | 2:45 - 3:30 | Click **Scenario Compare** tab | Click **Run Scenario Comparison**. Show the comparative matrix across **Cost-First**, **Balanced**, and **Service-First**. Point out the empirical trade-off: Cost-First saves freight ($50,150.99), while Service-First maximizes customer fulfillment (91.74%). Point out that Expiry Waste is honestly labeled **Not Modeled**. |
| **7. Planning History & Export** | 3:30 - 4:00 | Click **Planning History** tab | Show the audit trail of persisted runs. Click **Inspect** to review past shipments. Click **Download Run CSV** and open the exported file to demonstrate RFC 4180 formatting, metadata headers, and OWASP formula injection neutralization. |

---

## E. Empirical Validation Results

The following metrics were measured on the deterministic seed `42` dataset (7-day horizon, 39,878 units total replenishment demand considered):

| Metric | Cost-First Profile | Balanced Profile | Service-First Profile | Deterministic Greedy Baseline |
| :--- | :---: | :---: | :---: | :---: |
| **Solver Status** | `OPTIMAL` | `OPTIMAL` | `OPTIMAL` | Deterministic Heuristic |
| **Total Demand Considered** | 39,878 u | 39,878 u | 39,878 u | 39,878 u |
| **Fulfilled Units** | 35,963 u | 36,583 u | 36,583 u | 36,583 u |
| **Unmet Demand Units** | 3,915 u | 3,295 u | 3,295 u | 3,295 u |
| **Network Fulfillment Rate** | **90.18%** | **91.74%** | **91.74%** | **91.74%** |
| **Total Transportation Cost** | **$50,150.99** | **$52,816.51** | **$52,812.09** | **$54,085.66** |
| **Average Cost / Fulfilled Unit** | **$1.3945 / u** | **$1.4437 / u** | **$1.4436 / u** | **$1.4784 / u** |
| **Recommended Shipment Lines** | 764 lines | 774 lines | 774 lines | 774 lines |
| **Destinations Served** | 50 / 50 | 50 / 50 | 50 / 50 | 50 / 50 |
| **Solver Runtime** | 0.51s | 0.16s | 0.26s | < 0.05s |
| **12-Invariant Verifier** | `FEASIBLE` | `FEASIBLE` | `FEASIBLE` | Validated |

---

## F. Optimization vs. Greedy Baseline Analysis

### 1. Cost-First vs. Greedy Baseline
* **Freight Cost Reduction**: Cost-First achieves **$50,150.99** vs. Baseline **$54,085.66**, delivering an operational freight reduction of **-$3,934.67 (-7.28%)**.
* **Trade-off**: It deliberately trims 620 units (-1.56%) of long-haul, margin-diluting shipments while strictly satisfying the configured &ge; 80% fulfillment floor (delivering 90.18%).

### 2. Service-First vs. Greedy Baseline
* **Fulfillment Parity**: Both Service-First and the Greedy Baseline fulfill **36,583 units (91.74%)**, which represents the mathematical maximum allocatable supply across the network.
* **Intelligent Routing Savings**: In Stage 2 of the lexicographic solve, Service-First optimizes routing across all eligible hubs without sacrificing a single unit of service, delivering **-$1,273.57 (-2.35%)** lower freight cost than the myopic greedy heuristic.

### 3. Balanced vs. Service-First
* **Freshness Lead-Time Penalty**: The Balanced profile incorporates a lead-time transit penalty ($0.20/day/unit), routing select shipments through faster transit corridors to preserve shelf life at a minor freight delta of +$4.42 across the entire network.

---

## G. Known Limitations & Architectural Disclosures

1. **Simulated FMCG Data**: Historical demand across 800 corridors is deterministically generated using day-of-week seasonality, Poisson daily orders, and normal lead times (seed: 42).
2. **GAP-1 (Store On-Hand Stock = 0)**: Retail destination store stock is currently not modeled in the database schema and is assumed to be 0 units.
3. **GAP-2 (In-Transit Dispatches = 0)**: Confirmed orders currently in transit are not tracked and treated as 0 units. Consequently, gross replenishment equals the full threshold (LTD + Safety Stock).
4. **Retail Expiry Waste Unmodeled**: Shelf-life expiry is enforced at warehouse sourcing via FEFO batch dates. Retail shelf expiry shrinkage is unmodeled due to lack of store POS turnover feeds and is explicitly labeled **Not Modeled**.
5. **Advisory Plan Disclaimer**: Optimization outputs represent advisory shipment schedules; generating a plan does not deduct physical inventory from warehouse batches.

---

## H. Troubleshooting & FAQ

| Problem | Root Cause | Verified Remedy |
| :--- | :--- | :--- |
| **"Backend Disconnected" badge on Navbar** | FastAPI backend is not running on port 8000 | Start backend: `.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir services/api --port 8000` |
| **"Failed to load inventory batches"** | SQLite database file not found or unseeded | Run: `.venv\Scripts\python.exe scripts/seed_demo_data.py` |
| **`TARGET_UNACHIEVABLE` solver outcome** | Cost-First minimum fulfillment floor set higher than network capacity | Lower fulfillment floor slider (e.g. 80%) or check **Unconstrained Opt-In** checkbox |
| **`playwright test` timeout error** | Backend was not started prior to launching browser tests | Ensure backend is running at `http://127.0.0.1:8000` before executing `npx playwright test` |
