export interface Warehouse {
  id: number;
  code: string;
  name: string;
  city: string;
  state: string;
  capacity_units: number;
  latitude: number;
  longitude: number;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: string;
  shelf_life_days: number;
  unit_cost: number;
  unit_price: number;
  storage_temp_c: number;
  weight_kg: number;
}

export interface InventoryOverview {
  total_products: number;
  total_warehouses: number;
  total_destinations: number;
  total_units_on_hand: number;
  dataset_version: string;
  warehouses: Warehouse[];
  products: Product[];
}

export interface Shipment {
  id: number;
  source_warehouse_code: string;
  destination_code: string;
  destination_name: string;
  product_sku: string;
  product_name: string;
  recommended_units: number;
  unit_transport_cost: number;
  total_transport_cost: number;
  estimated_expiry_risk_pct: number;
  reasoning: string;
}

export interface StockoutAlert {
  destination_code: string;
  destination_name: string;
  product_sku: string;
  current_inventory_days: number;
  forecasted_daily_demand: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
}

export interface PlanMetrics {
  total_shipped_units: number;
  total_transport_cost: number;
  avg_expiry_risk_pct: number;
  stockouts_prevented: number;
  destinations_at_risk: number;
}

export interface PlanResponse {
  run_code: string;
  dataset_version: string;
  forecast_identifier: string;
  solver_status: string;
  created_at: string;
  metrics: PlanMetrics;
  shipments: Shipment[];
  stockout_risks: StockoutAlert[];
}

export interface PlanRequest {
  dataset_version_id?: number;
  forecast_horizon_days?: number;
  parameters?: {
    transport_weight?: number;
    stockout_penalty_weight?: number;
    expiry_risk_weight?: number;
    max_solver_time_seconds?: number;
  };
}

export interface HealthStatus {
  status: string;
  environment: string;
  database_connected: boolean;
  version: string;
  active_dataset_version?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/api/v1/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function fetchInventoryOverview(): Promise<InventoryOverview> {
  const res = await fetch(`${API_BASE}/api/v1/inventory/overview`);
  if (!res.ok) throw new Error("Failed to load inventory overview");
  return res.json();
}

export async function executePlanRun(payload: PlanRequest = {}): Promise<PlanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/planning/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Optimization planning run failed");
  }
  return res.json();
}
