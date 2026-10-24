# StockWise AI — Data Layer Audit & Hardening Plan

## 1. Executive Summary

An audit of the initial StockWise AI backend revealed a solid architectural foundation (Pydantic v2 schemas, SQLAlchemy 2.0 ORM, Alembic migrations, and OR-Tools linear solver integration). However, several data entities, schema constraints, and inventory accounting definitions required strengthening to support production-grade FMCG distribution intelligence.

---

## 2. Audit Findings & Gap Analysis

| Area | Current Implementation | Required State | Severity / Impact |
| :--- | :--- | :--- | :--- |
| **Routes Entity** | Distances computed on-the-fly in `solver.py`. No database persistence for routes. | First-class `Route` model with `origin_warehouse_id`, `destination_id`, `unit_transport_cost`, `lead_time_days`, `is_active`. | High — Cannot model route disruptions or lead time constraints. |
| **Demand History** | Generated on-the-fly in `forecaster.py`. No historical records. | `DailyDemandHistory` model storing at least 120 days of daily demand per product and destination. | High — Cannot train or validate forecasting models against empirical history. |
| **Inventory Batch Attributes** | `InventoryItem` has `on_hand_units`, `reserved_units`, `expiry_date`. | Add `unit_cost`, `received_date`, `batch_status` ('AVAILABLE', 'QUARANTINED', 'EXPIRED', 'DEPLETED'), and DB CheckConstraints. | Medium — Inability to track stock age, quarantine batches, or batch costs. |
| **Throughput Capacities** | Warehouses have volumetric capacity. Destinations have no capacity. | Add `daily_dispatch_capacity_units` to Warehouses and `daily_receiving_capacity_units` to Destinations. | Medium — Cannot prevent warehouse or store dock bottlenecks. |
| **Product Specifications** | SKU, name, category, shelf life, cost, price, temp, weight. | Add `unit_of_measure`, `holding_cost_per_day`, `lost_sales_penalty`. | Low-Medium — Required for multi-period holding cost and penalty modeling. |
| **Inventory Accounting** | `max(0, on_hand - reserved)` calculated without filtering expired batches. | Strict accounting hierarchy: On-Hand, Reserved, Available, Expired, and Usable stock. | High — Prevents allocating expired stock to shipments. |
| **Dataset Scale** | 16 destinations, no demand history. | 50 destinations, 120+ days of demand history, realistic edge cases. | Medium — Realistic evaluation of network optimization. |

---

## 3. Inventory Accounting Hierarchy

To avoid ambiguity, StockWise AI strictly enforces the following accounting formulas:

1. **On-Hand Inventory ($I_{OH}$)**: Total physical units currently held in warehouse storage.
2. **Reserved Inventory ($I_R$)**: Stock committed to open orders or pending movements. Constraint: $0 \le I_R \le I_{OH}$.
3. **Available Inventory ($I_A$)**: Unreserved physical inventory.
   $$I_A = \max(0, I_{OH} - I_R)$$
4. **Expired Inventory ($I_{EXP}$)**: Stock where $\text{expiry\_date} \le \text{as\_of\_date}$ or $\text{status} = \text{'EXPIRED'}$.
5. **Usable Inventory ($I_U$)**: Unexpired, unreserved, non-quarantined stock with shelf life strictly exceeding transit lead time plus safety threshold:
   $$I_U = \begin{cases} I_A & \text{if } \text{status} = \text{'AVAILABLE'} \land \text{expiry\_date} > (\text{as\_of\_date} + \text{lead\_time}) \\ 0 & \text{otherwise} \end{cases}$$
6. **Incoming Inventory ($I_{INC}$)**: Units in transit, arriving at future timestamp $t_{arrival}$.
