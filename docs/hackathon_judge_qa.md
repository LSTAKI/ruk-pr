# StockWise AI — Technical Judge Q&A Guide

> **Document Purpose**: Authoritative, technically rigorous, and defensible answers to 20 critical questions likely to be posed by hackathon judges and enterprise supply chain architects.  
> **Repository Context**: Triwizathon Problem Statement 2 (FMCG Distribution Intelligence & Inventory Optimization).  
> **Key Benchmark Reference**: Deterministic Simulated FMCG Dataset (`seed: 42`, 7-day horizon, 39,878 units total replenishment demand).

---

### Q1. Why use Google OR-Tools (Mixed-Integer Programming) instead of heuristics, meta-heuristics (Genetic Algorithms), or generative AI / LLMs?
**Answer**:
* **Determinism & Reproducibility**: Mixed-Integer Linear Programming (MILP) solved via branch-and-cut in Google OR-Tools guarantees deterministic, reproducible solutions. Given identical inputs, it always yields the exact same optimal allocation schedule.
* **Hard Constraint Satisfaction**: Supply chain networks operate under non-negotiable physical constraints (warehouse capacities, vehicle dispatch throughput, FEFO expiration dates, delivery cutoffs). LLMs hallucinate numbers and cannot mathematically guarantee inequality bounds ($Ax \le b$). Genetic algorithms can violate hard constraints and require arbitrary penalty tuning.
* **Global Optimality vs. Myopic Traps**: Greedy heuristics commit allocations sequentially and easily get trapped in local sub-optima. OR-Tools solves the multi-commodity network flow problem simultaneously across all 800 corridors, finding the global optimum.
* **Sub-Second Efficiency**: On an 800-corridor network with 200 routes, OR-Tools solves to proven optimality in under 0.50 seconds on a standard laptop CPU.

---

### Q2. What is the mathematical optimization objective formulation of the engine?
**Answer**:
Let $x_{w,d,p} \in \mathbb{Z}_{\ge 0}$ be the number of units of product $p$ shipped from warehouse $w$ to destination $d$, and $u_{d,p} \in \mathbb{Z}_{\ge 0}$ be unmet replenishment demand.
* **Cost-First Profile**:
  $$\min \sum_{w,d,p} c_{w,d} \cdot x_{w,d,p} + \sum_{d,p} (2 \cdot P_p) \cdot u_{d,p}$$
  $$\text{Subject to:} \quad \sum_{w,d,p} x_{w,d,p} \ge \lceil \gamma_{\min} \cdot \text{TotalDemand} \rceil \quad (\text{when policy active, default } \gamma_{\min} = 0.80)$$
  Where:
  - $c_{w,d} = \text{unit\_transport\_cost} \times \text{transport\_weight}$ (default weight $= 1.0$).
  - $2 \cdot P_p$: Unmet-demand penalty set to twice the product's lost-sales margin ($P_p = \text{lost\_sales\_penalty}$, default 5.0).
  - Minimum fulfillment floor: $\lceil 0.80 \times \text{TotalDemand} \rceil = 31,902 \text{ units}$. If `allow_unconstrained_cost_first` is enabled or floor $= 0.0$, the floor constraint is bypassed.
* **Service-First Profile (Lexicographic 2-Stage Priority Solve)**:
  * *Stage 1*: $\min \sum_{d,p} u_{d,p} \implies \text{yields global minimum unmet } u^*$.
  * *Stage 2*: $\min \sum_{w,d,p} c_{w,d} \cdot x_{w,d,p} \quad \text{s.t.} \quad \sum_{d,p} u_{d,p} \le u^*$.
* **Balanced Profile**:
  $$\min \sum_{w,d,p} \left(c_{w,d} + \lambda_{\text{LT}} \cdot T_{w,d}\right) x_{w,d,p} + \sum_{d,p} \left(\lambda_{\text{stockout}} \cdot P_p\right) u_{d,p}$$
  Where $T_{w,d}$ is route lead time (days), $\lambda_{\text{LT}} = \$0.20/\text{day/unit}$ (shelf-life freshness penalty), and $\lambda_{\text{stockout}} = 5.0$ (stockout priority multiplier). All terms are dimensionally consistent in $\$ / \text{unit}$.

**Crucial Distinction: Objective Value vs. Reported Freight Cost**:
The mathematical objective function value (which includes penalty multipliers like $2 \cdot P_p \cdot u_{d,p}$ or transit penalties $\lambda_{\text{LT}} \cdot T_{w,d} \cdot x_{w,d,p}$) is strictly an internal scalar score used by the branch-and-cut solver algorithm to navigate trade-offs. The business metric `total_transport_cost` reported on dashboards, API responses, and benchmark tables is **pure transportation freight**: $\sum_{(w,d,p)} x_{w,d,p} \cdot c_{w,d}$. Penalties are never added into the reported freight dollar total.

---

### Q3. How do the three profiles differ in practice, and when should a supply chain planner choose each?
**Answer**:
* **Service-First**: Prioritizes customer satisfaction above all else. It first exhausts all eligible network stock to achieve maximum possible fulfillment (91.74% on our dataset), then finds the cheapest routing to fulfill that quantity. Choose during peak sales seasons, holiday promotions, or high-contract SLA periods.
* **Cost-First**: Focuses on margin defense. It satisfies demand up to a configurable floor (e.g., 80% or 90%), but deliberately sheds low-margin, long-distance shipments where transport costs exceed product profit margins. On our benchmark, it fulfilled 90.18% while saving $2,661.10 in freight compared to Service-First ($50,150.99 vs. $52,812.09). Choose during high fuel price spikes or tight freight budget periods.
* **Balanced**: Blends transport cost and product freshness. It fulfills the same 91.74% as Service-First, but spends a minor +$4.42 premium across the network to prefer faster transit lanes, keeping perishable dairy and beverages fresher on store shelves.

---

### Q4. How is consumer demand estimated?
**Answer**:
* Demand is modeled per $(d, p)$ corridor using 120 days of historical demand.
* The system implements three time-series methods:
  1. **EWMA (Exponentially Weighted Moving Average)**: Default ($\alpha = 0.30$), dynamically weighting recent sales velocity while smoothing random Poisson noise.
  2. **Seasonal Naive**: Uses the demand value from 7 days prior ($y_{t-7}$) to capture strong day-of-week retail cycles.
  3. **Naive**: Rolling 7-day trailing average.
* **Holdout Validation**: The engine automatically performs chronological train/test split backtesting (e.g., training on the first 90 days, testing on the last 30 days) and computes MAE (Mean Absolute Error) and WAPE (Weighted Absolute Percentage Error).

---

### Q5. How is dynamic safety stock calculated, and how does it prevent stockouts?
**Answer**:
Safety stock is computed per corridor using the standard supply chain formula:
$$\text{SafetyStock}_{d,p} = z \times \sigma_{d,p} \times \sqrt{L_{w^*,d}}$$
Where:
* $z = 1.65$: Reflects a theoretical **95% cycle-service level** under normally distributed demand.
* $\sigma_{d,p}$: Sample standard deviation of daily demand from historical observations.
* $L_{w^*,d}$: Transit lead time (in days) from the primary eligible supplying warehouse.
* A fallback factor (0.25 $\times$ mean demand) is enforced if history is limited, and the result is rounded up to the nearest integer. Across our 800 corridors, continuous safety stock totals 10,744.93 units.

**Important Statistical Clarification**:
$z = 1.65$ represents a theoretical **cycle-service level** (the statistical probability that lead-time demand will not exceed replenishment stock during a replenishment cycle under normally distributed demand). It is **not** a guarantee of 95% aggregate network fulfillment (volume fill rate). Realized network fulfillment is bounded by physical warehouse inventory availability (e.g. the network-wide butter shortage on SKU-0004), non-normal Poisson demand clustering, and route eligibility constraints.

---

### Q6. How are expired and quarantined inventory batches handled?
**Answer**:
* In our database, inventory is tracked at the **batch/lot level** (`InventoryItem`) with fields for `on_hand_units`, `reserved_units`, `expiry_date`, and `batch_status` (`AVAILABLE`, `RESERVED`, `QUARANTINED`, `EXPIRED`).
* Before optimization, the inventory position engine executes `calculate_warehouse_available_stock`:
  * Quarantined batches (`batch_status == "QUARANTINED"`) contribute **0 usable units**.
  * Batches where `expiry_date <= as_of_date` contribute **0 usable units**.
  * Reserved units are deducted from on-hand stock.
* During route candidate generation, `compute_route_eligible_supply` evaluates route lead time: if a batch's expiry date is less than $\text{current\_date} + \lceil \text{lead\_time} \rceil + \text{min\_shelf\_life}$, it is disqualified from being shipped on that route.
* Our independent verifier (Invariant 3 & 10) re-verifies this rule outside the solver.

---

### Q7. How are warehouse dispatch and destination receiving throughput limits enforced?
**Answer**:
* In `solver.py`, daily throughput limits are added as hard linear inequality constraints:
  $$\sum_{d,p} x_{w,d,p} \le C_w^{\text{dispatch}} \quad \forall w \in W \quad (\text{e.g. } 15,000 \text{ units/day})$$
  $$\sum_{w,p} x_{w,d,p} \le C_d^{\text{receive}} \quad \forall d \in D \quad (\text{e.g. } 3,000 \text{ units/day})$$
* If a warehouse's total shipment allocation exceeds its daily dock loading capacity, the solver automatically re-routes excess volume to secondary eligible warehouses.
* Invariant 7 and 8 of the independent verifier confirm that neither limit is breached in the resulting schedule.

---

### Q8. How does the deterministic greedy baseline work?
**Answer**:
* The greedy baseline ([baseline.py](file:///c:/Users/dell/Desktop/ruk-pr/services/api/app/engine/optimize/baseline.py)) provides an unbiased benchmark.
* It evaluates under the **exact same physical constraints** as OR-Tools: identical usable stock bounds, route eligibility, delivery cutoffs, batch expiry at arrival, and warehouse/destination throughput capacities.
* It sorts demand requirements by urgency priority (Critical $\to$ High $\to$ Moderate $\to$ Low, then by demand volume). For each requirement, it greedily selects the eligible warehouse route with the lowest unit transportation cost ($c_{wd}$) and remaining supply.
* Because it commits allocations sequentially, early assignments lock up cheap inventory, forcing later destinations into expensive routes.

---

### Q9. How was the reported 2.35% freight cost reduction calculated?
**Answer**:
* Both Service-First and the Greedy Baseline fulfill **identical total quantities: 36,583 units (91.74%)** across the same 39,878 demanded units.
* Baseline Freight Cost: **$54,085.66** (Average: $1.4784/unit).
* Service-First Freight Cost: **$52,812.09** (Average: $1.4436/unit).
* Exact Dollar Savings: $\$54,085.66 - \$52,812.09 = \mathbf{\$1,273.57}$.
* Percentage Reduction:
  $$\frac{\$1,273.57}{\$54,085.66} \times 100\% = 2.3547\% \approx \mathbf{2.35\%}$$
* This reduction represents pure routing efficiency: zero units of customer service were sacrificed to achieve the $1,273.57 savings.

---

### Q10. How is the solution independently verified outside the solver?
**Answer**:
* The [SolutionVerifier](file:///c:/Users/dell/Desktop/ruk-pr/services/api/app/engine/verify/verifier.py) never trusts the solver's return code or self-reported metrics.
* It takes the raw list of recommended shipments and independently computes **12 mathematical invariants**:
  1. $x_{wdp} > 0$ strictly.
  2. $x_{wdp} \in \mathbb{Z}^+$ (whole integers).
  3. No expired or quarantined batches utilized.
  4. Total shipped per warehouse-SKU $\le$ verified usable stock.
  5. Total delivered per destination-SKU $\le$ demanded replenishment.
  6. Route active and exists in catalog.
  7. Warehouse dispatch throughput $\le C_w$.
  8. Destination receiving throughput $\le C_d$.
  9. Transit lead time $\le$ configured cutoff.
  10. Batch arrival shelf life exceeds delivery arrival date.
  11. Demand conservation: $\text{Fulfilled} + \text{Unmet} \equiv \text{Demanded}$.
  12. Independent cost check: $\sum (x \cdot c)$ matches reported cost within $\pm \$0.05$.
* A plan is marked `FEASIBLE` only if all 12 checks pass with zero violations.

---

### Q11. What does the solver status `OPTIMAL` mean? Does it guarantee zero stockouts?
**Answer**:
* `OPTIMAL` is the formal return status from Google OR-Tools branch-and-cut linear programming solver. It proves mathematically that **no feasible integer solution exists within the model's specified decision space and constraints that achieves a lower objective value**.
* **It does NOT mean zero stockouts**. If total physical stock across all warehouses for a given SKU is less than total network demand, stockouts are physically unavoidable. In our benchmark, `OPTIMAL` was achieved with 3,295 unmet units because the network has only 30 units of butter (SKU-0004) against 3,325 units of butter demanded. The solver fulfilled all 30 available units and correctly reported the remaining 3,295 units as physical deficit.
* **Scope of Optimality & Determinism**: Optimality is relative strictly to the mixed-integer programming objective function and the explicit modeled constraints (warehouse usable stock, route eligibility, delivery cutoffs, daily dispatch and receiving capacities). It does not claim that unmodeled operational variables (such as store backroom space or unexpected weather delays) are optimized. Solver determinism is empirically verified: branch-and-cut execution over identical inputs reliably reproduces the exact same allocation schedule within sub-second runtime (0.16s to 0.43s on standard laptop CPUs).

---

### Q12. What happens when network demand exceeds available warehouse stock?
**Answer**:
* In traditional systems without constraint-awareness, solvers either crash with an `INFEASIBLE` error or over-allocate stock that doesn't exist.
* In StockWise AI, demand balance is formulated with non-negative auxiliary unmet demand variables:
  $$\sum_w x_{w,d,p} + u_{d,p} = \text{Demand}_{d,p}, \quad u_{d,p} \ge 0$$
* If physical supply is exhausted, the solver assigns remaining demand to $u_{d,p}$, applies the lost-sales margin penalty, and outputs an explicit **Unmet Demand Schedule**. Planners can immediately see which stores will experience shortages and trigger emergency factory production or vendor purchase orders.

---

### Q13. Why is the dataset simulated, and how is it seeded?
**Answer**:
* Real enterprise FMCG distribution datasets contain proprietary pricing, customer locations, and margin structures that cannot be published in open-source hackathon repositories.
* We developed [DeterministicFMCGSimulator](file:///c:/Users/dell/Desktop/ruk-pr/services/api/app/engine/simulator/fmcg_generator.py) using `seed: 42`.
* It models realistic FMCG topologies:
  * 4 regional distribution centers with geolocated coordinates and real Haversine distances.
  * 16 SKUs across Dairy, Beverages, Snacks, and Personal Care.
  * 50 retail destinations across Supermarket, Wholesaler, and Convenience tiers.
  * Poisson daily demand with weekend spikes and day-of-week seasonality over 120 days.
  * Realistic edge cases: perishable dairy expiring in 3–5 days, warehouse stockout on butter, and remote route cutoffs.
* Re-running the seed script produces the **exact same 158 inventory items and 96,000 demand history rows** every time.

---

### Q14. What are the largest operational limitations of the current implementation?
**Answer**:
We openly document two known operational data gaps:
1. **GAP-1 (Store On-Hand Inventory = 0)**: In the current schema, retail store backroom inventory is not tracked; destinations are modeled with 0 initial inventory. Demand represents gross replenishment required over the lead-time window.
2. **GAP-2 (In-Transit Dispatches = 0)**: Shipments dispatched yesterday that are still on the highway are not tracked.
3. **Retail Shelf Expiry Shrinkage**: Expiry is strictly audited at warehouse dispatch (FEFO); retail store shelf spoilage is unmodeled due to lack of store register POS turnover feeds, and is labeled **Not Modeled**.
4. **Advisory Decision Support**: The system generates approved allocation schedules; it does not trigger automatic physical vehicle dispatches without planner confirmation.

---

### Q15. How would StockWise AI integrate with an enterprise ERP (e.g., SAP S/4HANA or Oracle SCM)?
**Answer**:
StockWise AI is architected as an API-first headless engine:
1. **Inbound Master Data**: Webhook or scheduled batch jobs consume SAP IDocs / OData endpoints (`/api/v1/inventory/batches` and `/api/v1/demand/history`) to ingest current bin stock and yesterday's store sales.
2. **Execution**: The planner triggers an optimization cycle via `POST /api/v1/planning/run`.
3. **Outbound Dispatches**: Once approved, the plan triggers outbound Advanced Shipping Notice (ASN) webhooks or writes directly into SAP `LFS / EDI 856` dispatch queues.
4. **Offline Resilience**: Because the engine runs local-first with SQLite, regional distribution hubs can continue generating optimized plans even during enterprise ERP WAN outages.

---

### Q16. Why is the current system advisory rather than executing automatic vehicle dispatches?
**Answer**:
* In enterprise supply chain management, fully autonomous dispatch execution without human-in-the-loop validation is rejected by risk compliance officers.
* Real-world logistics involves physical nuances not captured in database tables: sudden dock door mechanical failures, local driver strikes, sudden road closures, or bad weather alerts.
* StockWise AI provides **augmented intelligence**: it performs complex mathematical multi-commodity optimization in seconds, presents transparent driver explanations, and leaves final approval and exception overrides to human supply chain planners.

---

### Q17. What happens if an optimization scenario fails or is mathematically infeasible?
**Answer**:
* Infeasible states typically occur when a user sets conflicting constraints—for instance, setting Cost-First minimum fulfillment to 95% when total physical warehouse stock is only 91.74%, or setting a lead-time cutoff of 1.0 day for destinations 2,000 km away.
* The engine detects this upfront:
  1. It checks total network supply vs. the requested floor. If unattainable, it immediately returns `TARGET_UNACHIEVABLE` with an explanatory message: *"Available supply permits at most 91.74% fulfillment; requested 95.00% is mathematically unachievable."*
  2. The UI renders a red alert banner with actionable advice: lower the floor slider or enable the "Unconstrained Opt-In" toggle.
  3. The system never crashes, hangs, or fabricates mock allocations.

---

### Q18. How is benchmark repeatability established?
**Answer**:
* Repeatability is verified at three distinct levels:
  1. **Deterministic Seeding**: `DeterministicFMCGSimulator(seed=42)` guarantees identical input data.
  2. **Automated Benchmark Integrity Suite**: [test_benchmark_integrity.py](file:///c:/Users/dell/Desktop/ruk-pr/services/api/tests/test_benchmark_integrity.py) runs on every CI build, asserting that Cost-First fulfills exactly 35,963 units ($50,150.99), Service-First fulfills exactly 36,583 units ($52,812.09), and Greedy Baseline costs $54,085.66.
  3. **Isolated Database Testing**: In Prompt 9 audit phase, a clean database was created from scratch in a temporary directory; repeated optimization runs produced identical results down to the exact cent.

---

### Q19. How would StockWise AI scale to a tier-1 national distribution network (e.g., 500 warehouses, 10,000 retail stores, 5,000 SKUs)?
**Answer**:
* **Graph Decomposition & Regional Partitioning**: FMCG networks are naturally clustered by geographic zones (e.g., Northeast, Southeast, Midwest). Rather than solving one massive 25-billion variable monolithic MIP, the network can be decomposed into regional sub-problems solved in parallel.
* **Corridor Pruning**: Corridors with distances exceeding maximum truck driving limits (e.g., > 1,500 km for perishables) are pre-filtered, reducing the decision variable matrix by > 85%.
* **Database Scaling**: Upgrading SQLite to PostgreSQL with read replicas supports millions of historical demand rows and sub-second inventory snapshots.
* **Solver Tuning**: Google OR-Tools supports multi-threading (`solver.SetNumThreads(N)`) and high-performance commercial solvers (Gurobi / CPLEX) via the identical OR-Tools wrapper interface without rewriting a single line of business logic.

---

### Q20. What is the immediate next technical step toward production readiness?
**Answer**:
1. **Closing GAP-1 & GAP-2**: Add a `DestinationStockSnapshot` table and `InTransitDispatch` tracking pipeline.
2. **Multi-Period Rolling Horizon MIP**: Extend the current static single-period planning window into a 14-day rolling horizon formulation with multi-period inventory holding costs and scheduled factory replenishment arrivals.
3. **Containerized Deployment**: Deploy backend via Docker / Kubernetes with Redis queue workers for background scenario evaluations.
4. **Role-Based Access Control (RBAC)**: Implement JWT authentication distinguishing Regional Planners (who view and edit local corridors) from Executive Directors (who approve cross-network budgets).
