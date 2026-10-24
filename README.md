# StockWise AI

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg?logo=next.js)](https://nextjs.org)
[![OR-Tools](https://img.shields.io/badge/Google-OR--Tools-blue.svg)](https://developers.google.com/optimization)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**StockWise AI** is an AI-powered, local-first FMCG Distribution Intelligence and Inventory Optimization Engine.

It empowers FMCG supply chain planners to make automated, mathematically sound distribution decisions:
- **What products to ship & exact batch quantities**.
- **Which regional warehouse should supply each retail destination**.
- **Which destinations are at imminent risk of stockouts**.
- **How shipping decisions impact transportation costs, service levels, and shelf-life expiry wastage**.

---

## Architecture & Technology Stack

| Domain | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript (Strict) | Interactive planner dashboard |
| **Styling** | Tailwind CSS with design system tokens | Modern responsive UI |
| **Data Fetching** | TanStack React Query v5 | Efficient caching & server-state management |
| **Visualizations** | Recharts & Lucide Icons | Warehouse capacity and network telemetry |
| **Backend** | Python 3.11 - 3.13, FastAPI | High-performance asynchronous API service |
| **Solver** | Google OR-Tools (Linear Solver / MIP) | Deterministic distribution optimization |
| **ORM & DB** | SQLAlchemy 2.0, Alembic, SQLite3 | Persistent local-first relational storage |
| **Data Engine** | Pandas & NumPy | Fast array calculation & deterministic simulation |
| **Testing** | pytest, Vitest, React Testing Library, Playwright | Backend and frontend quality assurance |

---

## Directory Structure

```text
stockwise-ai/
├── apps/
│   └── web/                   # Next.js App Router planner dashboard
├── services/
│   └── api/                   # FastAPI backend service
│       ├── app/
│       │   ├── routes/        # Thin API route handlers
│       │   ├── schemas/       # Typed Pydantic v2 schemas
│       │   ├── db/            # SQLAlchemy 2.0 models & session
│       │   └── engine/        # Independent core business modules
│       │       ├── simulator/ # Deterministic dataset generator
│       │       ├── forecast/  # Demand forecasting module
│       │       ├── position/  # Inventory position & stockout risks
│       │       ├── validation/# Boundary & integrity validator
│       │       ├── optimize/  # Google OR-Tools solver
│       │       ├── verify/    # Independent feasibility verifier
│       │       └── explain/   # Decision reasoning attribution
│       ├── alembic/           # Database schema migrations
│       └── tests/             # Backend pytest suite
├── data/
│   ├── demo/                  # Inspectable JSON/CSV demo datasets
│   └── stockwise.db           # Persistent SQLite database file
├── docs/                      # Architectural documentation
├── scripts/
│   ├── verify_environment.py  # Dependency verification script
│   └── seed_demo_data.py      # Seed demo FMCG dataset (seed: 42)
├── docker-compose.yml         # Containerized local execution
├── .env.example               # Environment variables template
├── .gitignore                 # Repository ignore rules
└── README.md                  # This file
```

---

## Quickstart Guide

### 1. Prerequisites Check

Verify that your developer machine satisfies the requirements:

```bash
# Cross-platform check
python scripts/verify_environment.py
```

*Requirements:*
- Python `>= 3.11` (Tested on Python 3.11, 3.12, 3.13)
- Node.js `>= 18` (Node.js 20 or 24 recommended)
- npm `>= 9`
- SQLite3 (Standard in Python)

---

### 2. Option A: Local Run (No-Docker)

#### Step 1: Backend Setup
```bash
# 1. Create and activate a Python virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 2. Install backend dependencies
pip install -r services/api/requirements.txt

# 3. Create .env from template
copy .env.example .env    # On Windows
cp .env.example .env      # On Linux/macOS

# 4. Run database migrations
alembic -c services/api/alembic.ini upgrade head

# 5. Seed deterministic FMCG demo dataset (seed: 42)
python scripts/seed_demo_data.py

# 6. Start the FastAPI backend server
uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000 --reload
```
*Backend API available at: `http://localhost:8000` (Docs at `http://localhost:8000/docs`)*

#### Step 2: Frontend Setup
In a new terminal window:
```bash
# 1. Navigate to the web app
cd apps/web

# 2. Install dependencies
npm install

# 3. Run the development server
npm run dev
```
*Frontend Dashboard available at: `http://localhost:3000`*

---

### 3. Option B: Docker Compose

If Docker Engine is installed on your system:

```bash
# 1. Build and run backend, frontend, and persistent volume
docker compose up --build

# 2. Seed demo data inside the running backend container
docker compose exec backend python /app/../../scripts/seed_demo_data.py
```

---

## Health Check & Verification Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `http://localhost:8000/health` | GET | Basic container health check |
| `http://localhost:8000/api/v1/health` | GET | Detailed DB connection & active dataset tag check |
| `http://localhost:8000/api/v1/inventory/overview` | GET | Network warehouse & inventory status (On-Hand, Reserved, Available, Usable) |
| `http://localhost:8000/api/v1/inventory/batches` | GET | Paginated inventory batches with lot status & expiry |
| `http://localhost:8000/api/v1/routes` | GET | Paginated transportation routes with freight costs & lead times |
| `http://localhost:8000/api/v1/demand/history` | GET | 120+ days of empirical/simulated daily demand history |
| `http://localhost:8000/api/v1/planning/run` | POST | Triggers linear distribution optimization run |
| `http://localhost:8000/api/v1/planning/runs` | GET | Lists historical planning runs and solver outcomes |

---

## Running the Automated Test Suites

### Backend Unit & Integration Tests (pytest)
```bash
# Run all 182 backend tests across data layer, forecaster, replenishment, optimizer, and verifier
.venv/Scripts/python -m pytest services/api/tests -v
```

### Frontend Unit & Component Tests (Vitest)
```bash
# Run all 19 frontend unit tests covering navigation, overview, inventory explorer, forecasting, replenishment, optimizer, scenarios, formula injection, and CSV export
cd apps/web
npm test
```

### End-to-End Browser Tests (Playwright)
```bash
# Ensure local backend is running (uvicorn app.main:app --app-dir services/api --port 8000)
cd apps/web
npx playwright test
```

### TypeScript Compile & Production Build
```bash
cd apps/web
npx tsc --noEmit
npm run build
```

---

## Interactive Planner Dashboard (Next.js 15)

StockWise AI includes an enterprise-grade distribution intelligence control tower with 7 interconnected operational modules:
1. **Overview Dashboard**: High-level network telemetry, 4-tier inventory accounting (Physical on-hand, Reserved, Available, Usable), replenishment alerts, latest solver run status, and warehouse capacity distributions.
2. **Inventory Explorer**: Batch-level inventory ledger with regional warehouse, SKU, and batch status filters (`AVAILABLE`, `RESERVED`, `QUARANTINED`, `EXPIRED`), physical vs. usable accounting, and FEFO expiry badges.
3. **Demand Forecasting**: Interactive corridor time-series selector (product × destination), algorithm picker (`naive`, `ewma`, `seasonal_naive`), 7/14/30-day horizons, actual vs forecast Recharts curve, and holdout backtest evaluation (MAE & WAPE).
4. **Replenishment Planner**: Safety-stock reorder requirements ledger with lead-time demand, risk tiers (`Critical`, `High`, `Moderate`, `Low`), explanation drawer, and explicit GAP-1/GAP-2 data gap disclosures.
5. **Optimizer Planner**: Interactive MIP solver controls for `balanced`, `service_first`, and `cost_first` profiles, lead-time delivery cutoffs, minimum fulfillment floors, solver status banners, shipment recommendations, unmet demand analysis, and 12-invariant verifier audit reports.
6. **Scenario Comparison**: Side-by-side comparative matrix evaluating trade-offs across Cost-First, Balanced, and Service-First formulations under identical network constraints.
7. **Planning History & Export**: Complete chronological audit log of all persisted planning runs with one-click detail inspector and RFC 4180 CSV export.

---

## Hackathon Presentation & Demonstration Package

The complete presentation and demonstration package for Triwizathon Problem Statement 2 is available in `docs/`:
1. 📊 **[Executive Presentation Slide Deck (docs/StockWise_AI_Hackathon_Presentation.pptx)](docs/StockWise_AI_Hackathon_Presentation.pptx)**: 10-slide widescreen presentation detailing problem statement, architecture, mathematical formulations, empirical benchmarks, and production roadmap.
2. 🎙️ **[5-Minute Live Demonstration Script (docs/hackathon_demo_script.md)](docs/hackathon_demo_script.md)**: Second-by-second conversational walkthrough with exact UI clicks and talk tracks.
3. 🧠 **[Technical Judge Q&A Guide (docs/hackathon_judge_qa.md)](docs/hackathon_judge_qa.md)**: 20 comprehensive, defensible answers to deep architectural and mathematical questions.
4. 📑 **[Hackathon Validation & Demonstration Guide (docs/hackathon_demo.md)](docs/hackathon_demo.md)**: Complete benchmark methodology, empirical results, mathematical formulas, and 12-invariant verifier audit.

---

## Key Architectural Invariants

1. **Decoupled Datasets & Plans**: Raw inventory batches in `InventoryItem` are strictly separated from optimization runs in `PlanningRun`. Scenarios never mutate baseline source records.
2. **Deterministic Simulation**: Seed `42` produces identical warehouse coordinates, product catalogs, and batch expiry dates every time.
3. **Transparent Optimization**: Google OR-Tools solves the linear program directly without relying on probabilistic LLM hallucination for shipping quantities.
4. **Local-First & Offline**: Zero external network or cloud DB calls are executed during runtime.
