# StockWise AI — 5-Minute Live Demonstration Script

> **Context**: Live Hackathon Presentation for Triwizathon Problem Statement 2 (FMCG Distribution Intelligence & Inventory Optimization).  
> **Presenter Target Time**: 5:00 minutes (with 2 minutes Q&A buffer).  
> **Active Dataset**: Deterministic Simulated FMCG Network (`seed: 42`, version `v1.0-seed-42`).  
> **Environment**: Local-First (Frontend: `http://localhost:3000`, Backend: `http://127.0.0.1:8000`).

---

## Pre-Demo Checklist (Do Before Taking the Stage)
1. **Backend Server Running**: Confirm `uvicorn` is active on port 8000.  
   `curl http://127.0.0.1:8000/api/v1/health` &rarr; `{"status":"ok","database_connected":true}`.
2. **Frontend Dev Server Running**: Open `http://localhost:3000` in Google Chrome (fullscreen: `F11`).
3. **Database Seeded**: Confirm dataset tag displays `Simulated FMCG v1.0` in the top right.

---

## 0:00 – 0:35 | Hook & Operational Problem Statement

**Screen**: Overview Dashboard (`http://localhost:3000`)

> **Spoken**:  
> "Good morning, judges. In the FMCG distribution industry, supply chain planners face an intractable daily puzzle every morning across multi-echelon networks. 
> 
> Regional warehouses hold uneven inventory—some hubs are overflowing while peripheral hubs face immediate stockout risks. Perishable dairy and beverages are racing against expiration dates, and shipping products from distant warehouses incurs severe freight penalties. Today, most planners rely on intuition and fragmented spreadsheets.
> 
> We built **StockWise AI**—an AI-powered, local-first FMCG distribution intelligence and inventory optimization engine. It connects statistical time-series demand forecasting with dynamic multi-echelon safety stock, and solves the distribution allocation problem using Google OR-Tools Mixed-Integer Programming, validated by an independent 12-invariant mathematical verifier.
> 
> Let's see it in action."

---

## 0:35 – 1:15 | 4-Tier Inventory Accounting & FEFO Policy

**Action**: Click the **Inventory Explorer** tab on the top navigation bar.

> **Spoken**:  
> "Before optimizing dispatches, a supply chain engine must know what is truly usable. In StockWise AI, we enforce strict 4-tier inventory accounting:
> 1. Physical on-hand stock in warehouse bins.
> 2. Reserved units already committed to prior orders.
> 3. Available stock.
> 4. And crucially, **Usable Stock**.
> 
> Notice this filter. If I filter our batch ledger by `QUARANTINED`... *(click QUARANTINED filter)* ...notice that while on-hand units exist, the system calculates exactly **0 Usable Units**. Quarantined lots and expired batches are mathematically barred from being allocated to any shipment. Furthermore, our FEFO logic calculates remaining shelf-life against specific route transit lead times, so batches expiring before arrival can never be dispatched."

---

## 1:15 – 2:00 | Demand Forecasting & Backtesting

**Action**: Click the **Demand Forecast** tab.

> **Spoken**:  
> "Next, how do we anticipate demand? StockWise AI continuously models order histories across all 800 product-destination corridors in our network.
> 
> Let's select Corridor `PRD-MILK` shipping to `DST-001` (Sacramento Capitol Foods). We'll choose **EWMA** with an alpha smoothing factor of 0.30 over a **7-day horizon**, and click **Generate Forecast**. *(Click Generate Forecast button)*.
> 
> Instantly, the engine visualizes the 120-day historical demand actuals followed by the forward-looking forecast curve. We don't just generate numbers—we audit them. If I click **Run Backtest Evaluation**, the system runs an automated chronological holdout backtest, reporting a Mean Absolute Error (MAE) and Weighted Absolute Percentage Error (WAPE). This gives planners empirical confidence in their demand baseline."

---

## 2:00 – 2:45 | Multi-Echelon Replenishment & Stockout Risks

**Action**: Click the **Replenishment** tab.

> **Spoken**:  
> "A critical distinction in StockWise AI is that **Forecasted Consumer Demand is not Replenishment Requirement**.
> 
> Here in the Replenishment Planner, the engine converts daily forecast means into exact replenishment thresholds using two factors:
> 1. **Lead-Time Demand**: The demand expected to occur during the transit window from the fastest eligible warehouse.
> 2. **Dynamic Safety Stock**: Calculated using $z \times \sigma \times \sqrt{L}$ at a 95% non-stockout target.
> 
> Notice our transparent operational disclosure banner: in this demo, destination store inventory and in-transit shipments are modeled as zero (documented as GAP-1 and GAP-2), meaning the gross replenishment equals the full threshold.
> 
> Notice these risk flags: rows with zero cover days are categorized as **Critical**. If I click **Details** on any row, an explanation drawer breaks down the exact daily mean, transit days, and safety stock units that created that requirement."

---

## 2:45 – 3:45 | Constraint-Aware Optimization (Google OR-Tools)

**Action**: Click the **Optimizer Planner** tab.

> **Spoken**:  
> "Now, how do we fulfill this demand across 4 warehouses and 50 destinations?
> 
> We configure our optimization run. We offer three distinct mathematical profiles: **Cost-First**, **Balanced**, and **Service-First**. Let's select **Balanced**, with our standard 7-day horizon, and click **Run Local Optimizer**. *(Click Run Local Optimizer button)*.
> 
> In less than 0.3 seconds, Google OR-Tools formulates and solves the mixed-integer linear program. Look at this Outcome Card:
> - Solver Status: **OPTIMAL**—meaning the solver mathematically proved no better solution exists under this formulation.
> - Verifier Status: **Verifier: Feasible**.
> - Fulfillment Rate: **91.74%**, fulfilling **36,583 units** out of 39,878 demanded units.
> 
> Why were 3,295 units unmet? If we inspect the Unmet Demand table below, the system explains why: our network has a total physical stockout of butter (SKU-0004). The engine doesn't invent inventory—it reports physical supply exhaustion honestly.
> 
> If we expand any row in the recommended shipment table, our **Decision Explainer** explains the exact trade-off: why Warehouse 1 was selected over Warehouse 2 based on verified on-hand stock and a $0.35/unit lower freight rate."

---

## 3:45 – 4:30 | Scenario Comparison & Independent Verification

**Action**: Click the **Scenario Compare** tab, then click **Run Scenario Comparison**.

> **Spoken**:  
> "No supply chain operates on a single assumption. Here in Scenario Compare, we benchmark all three profiles side-by-side against our deterministic Greedy Baseline under identical physical constraints:
> 
> Look at the numbers:
> 1. **Service-First vs. Greedy Baseline**: Both achieve the network's maximum physical ceiling of **36,583 fulfilled units (91.74%)**. However, the greedy heuristic costs **$54,085.66**, while our Service-First MIP optimizer achieves the exact same fulfillment for **$52,812.09**. That is a **$1,273.57 (2.35%) freight cost reduction**, achieved solely through smarter multi-commodity network routing!
> 2. **Cost-First**: If operating margin is priority, Cost-First delivers an average unit cost of **$1.3945/unit**, saving **$3,934.67 (7.27%)** in freight by trimming long-haul shipments while strictly exceeding our configured 80% fulfillment floor (delivering 90.18%).
> 
> Crucially, every single plan must pass our **Independent 12-Invariant Solution Verifier**. It re-checks batch expiry at arrival, warehouse daily dispatch limits (15,000 units), destination receiving limits (3,000 units), integer non-negativity, and reconciles every dollar of freight outside the solver."

---

## 4:30 – 5:00 | Audit Trail, Export & Closing

**Action**: Click the **Planning History** tab, then click **Export CSV** on the latest run.

> **Spoken**:  
> "Finally, traceability. Every planning execution is permanently logged in SQLite with its full parameter snapshot. 
> 
> Planners can inspect past runs, or click **Export CSV** to download an RFC 4180-compliant distribution schedule complete with OWASP formula injection neutralization, ready for immediate import into SAP or Oracle WMS.
> 
> To summarize: StockWise AI delivers:
> - Explainable, deterministic forecasting.
> - Dynamic replenishment thresholding.
> - Constraint-aware Google OR-Tools optimization.
> - Independent mathematical verification.
> - And 100% local-first reliability with zero cloud dependencies.
> 
> Thank you, and we welcome your questions."
