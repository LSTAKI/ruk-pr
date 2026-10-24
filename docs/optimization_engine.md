# StockWise AI — Constraint-Aware Distribution Optimization Engine

## Overview

The Distribution Optimization Engine is the operational core of StockWise AI. It translates replenishment requirements, warehouse batch inventories, throughput limits, and active route networks into optimal, cost-efficient, and feasible distribution shipment plans.

The engine uses **Google OR-Tools Mixed-Integer Programming (MIP)** using the SCIP/CBC solver backend to ensure strictly discrete integer shipment decisions without continuous-rounding distortions.

---

## 1. Decision Variables

For each active, eligible transportation route connecting origin warehouse $w \in \mathcal{W}$ to retail destination $d \in \mathcal{D}$ for product $p \in \mathcal{P}$:

* **$x_{w, d, p} \in \mathbb{Z}_{\ge 0}$**: Non-negative integer number of units of product $p$ shipped from warehouse $w$ to destination $d$.
  * *Invariant:* If route $(w, d)$ does not exist, is marked inactive (`is_active == False`), or transit lead time exceeds the planning cutoff ($L_{w, d} > L_{\text{max}}$), the variable is **not instantiated** ($x_{w, d, p} \equiv 0$).
* **$u_{d, p} \in \mathbb{Z}_{\ge 0}$**: Non-negative integer unmet demand (shortage) of product $p$ at destination $d$.
* **$f_{d, p} \in \mathbb{Z}_{\ge 0}$**: Fulfilled demand units:
  $$f_{d, p} = \sum_{w: (w, d) \in \mathcal{R}_{\text{active}}} x_{w, d, p}$$

---

## 2. Mathematical Formulation & Constraints

### A. Warehouse-Product Supply Bound
Total units dispatched from warehouse $w$ for product $p$ cannot exceed available usable inventory:
$$\sum_{d: (w, d) \in \mathcal{R}_{\text{active}}} x_{w, d, p} \le \text{UsableSupply}_{w, p} \quad \forall w \in \mathcal{W}, p \in \mathcal{P}$$
Where $\text{UsableSupply}_{w, p}$ strictly excludes:
* Reserved units assigned to active orders.
* Expired batches ($\text{expiry\_date} \le \text{as\_of\_date}$).
* Quarantined or damaged batches.

### B. Destination-Product Demand Balance & Unmet Accounting
Shipment allocations and unmet shortages must reconcile strictly to the demand requirement:
$$\sum_{w: (w, d) \in \mathcal{R}_{\text{active}}} x_{w, d, p} + u_{d, p} = \text{Demand}_{d, p} \quad \forall d \in \mathcal{D}, p \in \mathcal{P}$$
* If no eligible routes exist to destination $d$, $u_{d, p} = \text{Demand}_{d, p}$ and $f_{d, p} = 0$.

### C. Warehouse Daily Dispatch Throughput Limit
Total units dispatched across all products and destinations must respect physical handling/dock limits:
$$\sum_{d \in \mathcal{D}} \sum_{p \in \mathcal{P}} x_{w, d, p} \le \text{DailyDispatchCapacity}_w \quad \forall w \in \mathcal{W}$$

### D. Destination Daily Receiving Throughput Limit
Total units received at a destination across all warehouses and products must respect store dock/intake limits:
$$\sum_{w \in \mathcal{W}} \sum_{p \in \mathcal{P}} x_{w, d, p} \le \text{DailyReceivingCapacity}_d \quad \forall d \in \mathcal{D}$$

### E. Route Eligibility & Delivery Lead-Time Cutoff
$$\text{If } (w, d) \notin \mathcal{R}_{\text{active}} \text{ or } L_{w, d} > L_{\text{max}} \implies x_{w, d, p} = 0$$

### F. Integrality
$$x_{w, d, p} \in \mathbb{Z}_{\ge 0}, \quad u_{d, p} \in \mathbb{Z}_{\ge 0}$$

---

## 3. Optimization Profiles & Objective Functions

The solver supports three configurable profiles that alter mathematical solver behavior:

### 1. Cost-First (`cost_first`)
Minimizes total freight cost while fulfilling demand when freight is economical relative to the lost-sales penalty:
$$\min \sum_{w, d, p} c_{w, d} \cdot x_{w, d, p} + \sum_{d, p} 2 \cdot \text{LostPenalty}_p \cdot u_{d, p}$$
* Prioritizes lowest-cost sourcing paths.
* Prevents unprofitable remote dispatch if freight exceeds lost-sales penalties.

### 2. Service-First (`service_first`)
Implements **lexicographic two-stage optimization**:
* **Stage 1 (Maximize Service Level):**
  $$\min \sum_{d, p} u_{d, p} \implies \text{Find minimal unmet demand } U^*$$
* **Stage 2 (Minimize Freight at Max Service):**
  Constrain $\sum_{d, p} u_{d, p} \le U^*$, then solve:
  $$\min \sum_{w, d, p} c_{w, d} \cdot x_{w, d, p}$$
* Guarantees maximum possible fulfillment across the network first, using freight cost strictly to break ties.

### 3. Balanced (`balanced` — Default)
Multi-objective compromise blending freight costs, stockout avoidance, and delivery transit speed:
$$\min \sum_{w, d, p} \left(c_{w, d} + 0.2 \cdot L_{w, d}\right) \cdot x_{w, d, p} + \sum_{d, p} 5 \cdot \text{LostPenalty}_p \cdot u_{d, p}$$

---

## 4. Deterministic Greedy Baseline Heuristic

Every optimization run executes a parallel **constraint-aware greedy baseline** on identical inputs:
1. Filters active routes and lead-time cutoffs.
2. Tracks remaining dispatch capacity, receiving capacity, and warehouse usable stock.
3. Sorts requirements by risk urgency (`Critical` > `High` > `Moderate` > `Low`) and quantity.
4. Selects the lowest unit freight cost warehouse route with available inventory and capacity.
5. Computes baseline metrics ($U_{\text{baseline}}$, $C_{\text{baseline}}$, $\text{FulfillmentRate}_{\text{baseline}}$).
6. Directly computes real delta improvements against the OR-Tools MIP plan.

---

## 5. Independent Solution Verification (12 Invariants)

The `SolutionVerifier` independently evaluates the plan without trusting solver status:
1. **Non-negative quantities:** $x_{w, d, p} > 0$.
2. **Integer quantities:** $x_{w, d, p} \in \mathbb{Z}$.
3. **No expired/quarantined stock:** Usable supply excludes ineligible batches.
4. **Warehouse supply bound:** $\sum_d x_{w, d, p} \le \text{UsableSupply}_{w, p}$.
5. **Demand fulfillment bound:** $\sum_w x_{w, d, p} \le \text{Demand}_{d, p}$.
6. **Route eligibility:** Only active routes in the network table are used.
7. **Dispatch capacity:** $\sum_{d, p} x_{w, d, p} \le \text{DailyDispatchCapacity}_w$.
8. **Receiving capacity:** $\sum_{w, p} x_{w, d, p} \le \text{DailyReceivingCapacity}_d$.
9. **Lead-time cutoff:** $L_{w, d} \le L_{\text{max}}$.
10. **Batch-level expiry feasibility:** Arrival dates do not violate shelf life.
11. **Demand reconciliation:** $\text{Fulfilled} + \text{Unmet} = \text{Demanded}$.
12. **Cost reconciliation:** $\sum (x_{w, d, p} \cdot c_{w, d}) = \text{Reported Total Transport Cost}$.

---

## 6. Solver Status Semantics

| Solver Status | Meaning | Action Taken |
|---|---|---|
| `OPTIMAL` | Mathematically proven global optimum found by MIP solver. | Full plan returned. |
| `FEASIBLE` | Feasible integer solution found before time limit expired. | Usable plan returned. |
| `INFEASIBLE` | Network constraints cannot be satisfied simultaneously. | Empty plan returned with full unmet demand list. |
| `TIMED_OUT` | Solver time limit reached with no integer solution found. | Reported explicitly without disguising failure. |
| `INVALID_INPUT` | Input network lists are empty or corrupted. | Rejected with clear error message. |
| `INTERNAL_ERROR` | Underlying solver engine failed to initialize. | Reported with diagnostic logs. |

---

## 7. Explainability Framework

Every shipment allocation receives a structured, factor-based explanation detailing:
* Units dispatched, destination, and product name.
* Route freight rate ($/unit) and transit lead time (days).
* Destination stockout risk tier (`Critical`, `High`, `Moderate`).
* Competing warehouse alternatives (e.g. why Warehouse B was not chosen: higher freight cost, longer lead time, or depleted inventory).

---

## 8. API Reference

### `POST /api/v1/planning/run` & `POST /api/v1/planning/optimize`

**Request Payload:**
```json
{
  "forecast_horizon_days": 7,
  "parameters": {
    "profile": "service_first",
    "max_lead_time_days": 3.0,
    "max_solver_time_seconds": 10,
    "transport_weight": 1.0,
    "stockout_penalty_weight": 5.0,
    "use_replenishment_engine": true
  }
}
```

**Response Payload Structure:**
* `run_code`: Unique UUID run code.
* `solver_status`: `OPTIMAL` or `FEASIBLE`.
* `metrics`: Total shipped units, transport cost, fulfillment rate, runtime.
* `shipments`: List of shipments with route costs, lead times, and empirical reasoning.
* `unmet_demands`: List of unfulfilled demand quantities per destination and SKU.
* `baseline_comparison`: Exact empirical comparisons with the greedy baseline.
* `verification`: 12-invariant independent verification report.

---

## 9. Known Data Gaps & Caveats

1. **GAP-1 (Destination Inventory):** Store-level on-hand is not recorded in the DB; destination initial inventory is assumed zero.
2. **GAP-2 (In-Transit Dispatches):** Confirmed in-transit shipments are not tracked in DB; incoming inventory is assumed zero.
3. **No Stock Mutation:** Running the optimization engine generates `PlanningRun` and `ShipmentRecommendation` records in the database, but **never mutates physical warehouse inventory** (`InventoryItem.on_hand_units` remains untouched).

---

## 10. Running Tests

```bash
# Run complete test suite (173 passing tests)
.venv\Scripts\python.exe -m pytest services\api\tests\ -v

# Run optimization engine test suite exclusively
.venv\Scripts\python.exe -m pytest services\api\tests\test_optimization_engine.py -v
```
