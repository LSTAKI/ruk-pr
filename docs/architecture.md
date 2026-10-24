# StockWise AI - System Architecture & Engineering Guide

## 1. High-Level Overview

**StockWise AI** is an AI-powered, local-first FMCG Distribution Intelligence and Inventory Optimization Engine.
It is specifically engineered to solve the complex multi-echelon FMCG supply chain challenge:
- Determining which products to ship and exact quantities.
- Determining which distribution center / warehouse should supply each retail store or wholesaler.
- Identifying destinations facing stockouts before shelves empty.
- Balancing transportation costs against shelf-life expiry risk and stockout penalties.

---

## 2. Local-First Engineering Principles

1. **Zero Cloud Database Dependencies**: Runs against SQLite3 with SQLAlchemy 2.0 and Alembic migrations.
2. **Deterministic FMCG Simulation**: Built-in deterministic generator using fixed random seeds (default `42`) to produce identical master data, batch lots, and expiry schedules.
3. **Decoupled Architecture**: Source inventory (`InventoryItem`) remains strictly decoupled from planning runs (`PlanningRun`) and shipping recommendations (`ShipmentRecommendation`). Baseline datasets are preserved intact across scenario runs.
4. **No LLMs Deciding Quantities**: Optimization decisions are computed using mathematical linear programming / MIP formulations powered by Google OR-Tools.
5. **Typed Contracts**: Strict TypeScript on Next.js 15 App Router and Pydantic v2 schemas on FastAPI.

---

## 3. Directory Structure

```
stockwise-ai/
├── apps/
│   └── web/                   # Next.js 15 App Router, React, Tailwind CSS, TanStack Query, Recharts
│       ├── app/               # App Router pages and layout
│       ├── components/        # UI components (KPISummary, InventoryChart, ShipmentTable, etc.)
│       ├── lib/               # Typed API client and utilities
│       ├── __tests__/         # Vitest + React Testing Library tests
│       └── e2e/               # Playwright end-to-end testing
├── services/
│   └── api/                   # Python 3.11+ FastAPI service
│       ├── app/
│       │   ├── db/            # SQLAlchemy 2.0 models, session, engine
│       │   ├── schemas/       # Typed Pydantic v2 request/response schemas
│       │   ├── routes/        # Thin route handlers (health, inventory, planning, scenarios)
│       │   └── engine/        # Independent core business modules
│       │       ├── simulator/ # Deterministic FMCG data generation
│       │       ├── forecast/  # Demand forecasting across horizon
│       │       ├── position/  # Inventory position & stockout risk detection
│       │       ├── validation/# Supply, demand, and warehouse capacity validator
│       │       ├── optimize/  # Google OR-Tools linear solver formulation
│       │       ├── verify/    # Independent feasibility and bound verifier
│       │       └── explain/   # Transparent driver-based attribution explainer
│       ├── alembic/           # Alembic database migrations
│       └── tests/             # Backend pytest test suite
├── data/
│   ├── demo/                  # Inspectable JSON/CSV demo dataset artifacts
│   └── stockwise.db           # Persistent SQLite database file
├── docs/                      # Architectural & design documentation
├── scripts/
│   ├── verify_environment.py  # Dependency & runtime verification script
│   └── seed_demo_data.py      # Deterministic demo seeder script
├── docker-compose.yml         # Containerized multi-service configuration
├── .env.example               # Template environment configuration
├── .gitignore                 # Monorepo git ignore rules
└── README.md                  # Comprehensive getting started guide
```

---

## 4. Optimization Engine Formulation

Let:
- $W$: Set of regional distribution centers (warehouses)
- $D$: Set of destination retail stores and wholesalers
- $P$: Set of FMCG product SKUs
- $x_{w, d, p} \ge 0$: Units of SKU $p$ shipped from warehouse $w$ to destination $d$

**Constraints**:
1. **Supply Limit**: For each $w \in W, p \in P$:
   $$\sum_{d \in D} x_{w, d, p} \le \text{AvailableSupply}_{w, p}$$
2. **Demand Target**: For each $d \in D, p \in P$:
   $$\sum_{w \in W} x_{w, d, p} \le \text{ForecastedDemand}_{d, p}$$

**Objective**:
$$\min \sum_{w, d, p} \left( C_{w, d}^{\text{transport}} \cdot \alpha \cdot x_{w, d, p} \right) - \sum_{d, p} \left( \text{StockoutPenalty}_p \cdot \beta \sum_{w} x_{w, d, p} \right)$$
where $\alpha$ is the freight weight, and $\beta$ is the service fulfillment weight.

---

## 5. Verification & Explanation

After solving, the output is passed to:
- **`SolutionVerifier`**: Independently confirms zero violations (non-negativity, capacity headroom, non-expired inventory).
- **`DistributionDecisionExplainer`**: Translates math variables into actionable planner explanations (e.g., freight cost trade-offs, regional hub proximity).
