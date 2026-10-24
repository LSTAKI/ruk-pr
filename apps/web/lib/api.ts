/**
 * StockWise AI - Typed Frontend API Client & Contracts
 * Synchronized with FastAPI Backend Pydantic Schemas.
 */

// ---------------------------------------------------------------------------
// Core Entity Schemas
// ---------------------------------------------------------------------------

export interface Warehouse {
  id: number;
  code: string;
  name: string;
  city: string;
  state: string;
  capacity_units: number;
  daily_dispatch_capacity_units: number;
  latitude: number;
  longitude: number;
}

export interface Destination {
  id: number;
  code: string;
  name: string;
  channel_type: string;
  city: string;
  state: string;
  daily_receiving_capacity_units: number;
  latitude: number;
  longitude: number;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: string;
  unit_of_measure: string;
  shelf_life_days: number;
  unit_cost: number;
  unit_price: number;
  holding_cost_per_day: number;
  lost_sales_penalty: number;
  storage_temp_c: number;
  weight_kg: number;
}

export interface InventoryItem {
  id: number;
  warehouse_id: number;
  product_id: number;
  batch_lot: string;
  on_hand_units: number;
  reserved_units: number;
  available_units?: number;
  usable_units?: number;
  unit_cost: number;
  expiry_date: string;
  received_date?: string;
  batch_status: "AVAILABLE" | "RESERVED" | "QUARANTINED" | "EXPIRED" | "DEPLETED" | string;
  warehouse_code?: string;
  product_sku?: string;
  product_name?: string;
}

export interface InventoryOverview {
  total_products: number;
  total_warehouses: number;
  total_destinations: number;
  total_units_on_hand: number;
  total_units_reserved: number;
  total_units_available: number;
  total_units_usable: number;
  dataset_version: string;
  warehouses: Warehouse[];
  products: Product[];
}

export interface InventoryBatchListResponse {
  total: number;
  limit: number;
  offset: number;
  batches: InventoryItem[];
}

export interface Route {
  id: number;
  origin_warehouse_id: number;
  destination_id: number;
  origin_warehouse_code?: string;
  destination_code?: string;
  destination_name?: string;
  unit_transport_cost: number;
  lead_time_days: number;
  distance_km: float;
  is_active: boolean;
}

type float = number;

export interface RouteListResponse {
  total: number;
  limit: number;
  offset: number;
  routes: Route[];
}

export interface DailyDemandHistory {
  id: number;
  destination_id: number;
  product_id: number;
  destination_code?: string;
  destination_name?: string;
  product_sku?: string;
  product_name?: string;
  demand_date: string;
  quantity_demanded: number;
  quantity_sold: number;
  is_simulated: boolean;
}

export interface DemandHistoryResponse {
  total: number;
  limit: number;
  offset: number;
  records: DailyDemandHistory[];
}

// ---------------------------------------------------------------------------
// Demand Forecasting Schemas
// ---------------------------------------------------------------------------

export interface ForecastRequest {
  product_id: number;
  destination_id: number;
  horizon_days?: 7 | 14 | 30;
  method?: "naive" | "ewma" | "seasonal_naive";
  ewma_alpha?: number;
  as_of_date?: string;
}

export interface DailyForecastValue {
  date: string;
  value: number;
}

export interface ForecastResponse {
  product_id: number;
  product_sku: string;
  destination_id: number;
  destination_code: string;
  generated_at: string;
  horizon_days: number;
  method: string;
  method_available: boolean;
  unavailability_reason?: string;
  daily_forecasts: DailyForecastValue[];
  total_demand: number;
  daily_mean_demand: number;
  forecasted_units: number;
  history_observations_used: number;
  warnings: string[];
  is_simulated_data: boolean;
}

export interface MethodEvalResult {
  method: string;
  method_available: boolean;
  unavailability_reason?: string;
  mae?: number;
  wape_pct?: number;
  wape_unavailable_reason?: string;
  n_evaluated: number;
  evaluation_start?: string;
  evaluation_end?: string;
}

export interface AggregateMethodSummary {
  method: string;
  series_with_method: number;
  mae_mean?: number;
  mae_min?: number;
  mae_max?: number;
  wape_mean_pct?: number;
  wape_min_pct?: number;
  wape_max_pct?: number;
  wape_series_with_zero_actuals: number;
}

export interface ForecastEvaluationResponse {
  n_series_evaluated: number;
  total_observations_evaluated: number;
  aggregate: Record<string, AggregateMethodSummary>;
  caveats: string[];
  series: Array<{
    product_id?: number;
    destination_id?: number;
    product_sku?: string;
    destination_code?: string;
    train_observations: number;
    test_observations: number;
    total_observations: number;
    evaluation_start?: string;
    evaluation_end?: string;
    methods: Record<string, MethodEvalResult>;
    warnings: string[];
  }>;
}

// ---------------------------------------------------------------------------
// Replenishment Engine Schemas
// ---------------------------------------------------------------------------

export interface SafetyStockResult {
  safety_stock_units: number;
  safety_stock_int: number;
  method_used: string;
  mean_daily_demand: number;
  stddev_daily_demand?: number;
  lead_time_days: number;
  observations_used: number;
  warnings: string[];
  is_simulated_data: boolean;
}

export interface ReplenishmentRequirement {
  product_id: number;
  product_sku: string;
  product_name: string;
  destination_id: number;
  destination_code: string;
  destination_name: string;
  lead_time_days: number;
  warehouse_code?: string;
  route_selection_reason: string;
  daily_mean_demand: number;
  lead_time_demand: number;
  forecast_method: string;
  forecast_warnings: string[];
  safety_stock: SafetyStockResult;
  replenishment_threshold: number;
  destination_usable_units: number;
  incoming_committed_units: number;
  projected_position: number;
  gross_replenishment: number;
  replenishment_qty: number;
  cover_days?: number;
  safety_stock_days?: number;
  risk_category: "Critical" | "High" | "Moderate" | "Low" | "InsufficientData" | string;
  reason_codes: string[];
  explanation: string;
  warnings: string[];
  history_observations_used: number;
}

export interface ReplenishmentSummaryResponse {
  generated_at: string;
  total: number;
  limit: number;
  offset: number;
  warehouses_evaluated: string[];
  as_of_date: string;
  requirements: ReplenishmentRequirement[];
  total_replenishment_units: number;
  critical_count: number;
  high_count: number;
  moderate_count: number;
  low_count: number;
  insufficient_data_count: number;
  caveats: string[];
}

export interface ReplenishmentSummaryRequest {
  warehouse_id?: number;
  product_id?: number;
  destination_id?: number;
  safety_stock_config?: {
    service_level_z?: number;
    fallback_factor?: number;
    min_safety_stock_units?: number;
  };
  forecast_method?: string;
  ewma_alpha?: number;
  risk_filter?: string;
  as_of_date?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Optimization and Planning Schemas
// ---------------------------------------------------------------------------

export interface OptimizationParameters {
  transport_weight?: number;
  stockout_penalty_weight?: number;
  expiry_risk_weight?: number;
  lead_time_penalty_weight?: number;
  min_fulfillment_rate?: number;
  allow_unconstrained_cost_first?: boolean;
  min_arrival_shelf_life_days?: number;
  max_solver_time_seconds?: number;
  profile?: "cost_first" | "service_first" | "balanced" | string;
  max_lead_time_days?: number | null;
  use_replenishment_engine?: boolean;
  ewma_alpha?: number;
  service_level_z?: number;
}

export interface PlanRequest {
  dataset_version_id?: number;
  forecast_horizon_days?: number;
  parameters?: OptimizationParameters;
  optimization_profile?: "cost_first" | "service_first" | "balanced" | string;
  max_lead_time_days?: number | null;
  min_fulfillment_rate?: number;
  allow_unconstrained_cost_first?: boolean;
  as_of_date?: string;
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
  estimated_expiry_risk_pct?: number | null;
  lead_time_days?: number;
  reasoning?: string;
}

export interface StockoutAlert {
  destination_code: string;
  destination_name: string;
  product_sku: string;
  current_inventory_days: number;
  forecasted_daily_demand: number;
  risk_level: string; // Critical, High, Moderate, Low
}

export interface UnmetDemand {
  destination_code: string;
  destination_name: string;
  product_sku: string;
  product_name: string;
  demanded_units: number;
  fulfilled_units: number;
  unmet_units: number;
  risk_category: string;
}

export interface BaselineComparison {
  baseline_total_units: number;
  baseline_total_cost: number;
  baseline_unmet_units: number;
  baseline_fulfillment_rate: number;
  optimized_total_units: number;
  optimized_total_cost: number;
  optimized_unmet_units: number;
  optimized_fulfillment_rate: number;
  units_difference: number;
  cost_difference: number;
  fulfillment_rate_difference: number;
}

export interface VerificationSummary {
  is_feasible: boolean;
  violations_count: number;
  violations: string[];
  recalculated_cost: number;
  recalculated_units: number;
  recalculated_fulfilled: number;
  recalculated_unmet: number;
}

export interface PlanMetrics {
  total_shipped_units: number;
  total_transport_cost: number;
  avg_expiry_risk_pct?: number | null;
  expiry_waste_modeled?: boolean;
  stockouts_prevented: number;
  destinations_at_risk: number;
  total_demanded_units?: number;
  total_unmet_units?: number;
  fulfillment_rate?: number;
  min_fulfillment_target_met?: boolean | null;
  solver_runtime_seconds?: number;
}

export interface PlanResponse {
  run_code: string;
  dataset_version: string;
  forecast_identifier: string;
  solver_status: "OPTIMAL" | "FEASIBLE" | "TARGET_UNACHIEVABLE" | "INFEASIBLE" | "TIMEOUT" | string;
  status_message?: string;
  created_at: string;
  metrics: PlanMetrics;
  shipments: Shipment[];
  stockout_risks: StockoutAlert[];
  unmet_demands?: UnmetDemand[];
  baseline_comparison?: BaselineComparison | null;
  verification?: VerificationSummary | null;
  data_quality_warnings?: string[];
  optimization_profile?: string;
}

export interface PlanningRunListItem {
  id: number;
  run_code: string;
  dataset_version_id: number;
  forecast_identifier: string;
  solver_status: string;
  total_transport_cost: number;
  total_shipped_units: number;
  stockout_risk_count: number;
  status: string;
  created_at: string;
}

export interface PlanningRunListResponse {
  total: number;
  limit: number;
  offset: number;
  runs: PlanningRunListItem[];
}

export interface HealthStatus {
  status: string;
  environment: string;
  database_connected: boolean;
  version: string;
  active_dataset_version?: string;
}

// ---------------------------------------------------------------------------
// API Client Functions with central error handling
// ---------------------------------------------------------------------------

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

async function handleResponse<T>(res: Response, fallbackMessage: string): Promise<T> {
  if (!res.ok) {
    let detail = fallbackMessage;
    try {
      const err = await res.json();
      detail = err.detail || err.message || JSON.stringify(err);
    } catch {
      detail = `${fallbackMessage} (${res.status} ${res.statusText})`;
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/api/v1/health`, { cache: "no-store" });
  return handleResponse<HealthStatus>(res, "Failed to connect to backend health endpoint");
}

export async function fetchInventoryOverview(): Promise<InventoryOverview> {
  const res = await fetch(`${API_BASE}/api/v1/inventory/overview`, { cache: "no-store" });
  return handleResponse<InventoryOverview>(res, "Failed to load inventory overview");
}

export async function fetchInventoryBatches(params?: {
  warehouse_id?: number;
  product_id?: number;
  batch_status?: string;
  limit?: number;
  offset?: number;
}): Promise<InventoryBatchListResponse> {
  const query = new URLSearchParams();
  if (params?.warehouse_id !== undefined) query.set("warehouse_id", String(params.warehouse_id));
  if (params?.product_id !== undefined) query.set("product_id", String(params.product_id));
  if (params?.batch_status) query.set("batch_status", params.batch_status);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));

  const url = `${API_BASE}/api/v1/inventory/batches${query.toString() ? `?${query.toString()}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  return handleResponse<InventoryBatchListResponse>(res, "Failed to load inventory batches");
}

export async function fetchWarehouses(): Promise<Warehouse[]> {
  const res = await fetch(`${API_BASE}/api/v1/inventory/warehouses`, { cache: "no-store" });
  return handleResponse<Warehouse[]>(res, "Failed to load warehouses");
}

export async function fetchDestinations(): Promise<Destination[]> {
  const res = await fetch(`${API_BASE}/api/v1/inventory/destinations`, { cache: "no-store" });
  return handleResponse<Destination[]>(res, "Failed to load destinations");
}

export async function fetchProducts(): Promise<Product[]> {
  const res = await fetch(`${API_BASE}/api/v1/inventory/products`, { cache: "no-store" });
  return handleResponse<Product[]>(res, "Failed to load products");
}

export async function fetchDemandHistory(params?: {
  destination_id?: number;
  product_id?: number;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}): Promise<DemandHistoryResponse> {
  const query = new URLSearchParams();
  if (params?.destination_id !== undefined) query.set("destination_id", String(params.destination_id));
  if (params?.product_id !== undefined) query.set("product_id", String(params.product_id));
  if (params?.start_date) query.set("start_date", params.start_date);
  if (params?.end_date) query.set("end_date", params.end_date);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));

  const url = `${API_BASE}/api/v1/demand/history${query.toString() ? `?${query.toString()}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  return handleResponse<DemandHistoryResponse>(res, "Failed to load demand history");
}

export async function generateForecast(payload: ForecastRequest): Promise<ForecastResponse> {
  const res = await fetch(`${API_BASE}/api/v1/forecast`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<ForecastResponse>(res, "Failed to generate demand forecast");
}

export async function evaluateForecast(payload?: {
  product_id?: number;
  destination_id?: number;
  ewma_alpha?: number;
  test_fraction?: number;
}): Promise<ForecastEvaluationResponse> {
  const res = await fetch(`${API_BASE}/api/v1/forecast/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  return handleResponse<ForecastEvaluationResponse>(res, "Failed to evaluate forecast models");
}

export async function fetchReplenishmentSummary(
  payload: ReplenishmentSummaryRequest = {}
): Promise<ReplenishmentSummaryResponse> {
  const res = await fetch(`${API_BASE}/api/v1/replenishment/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<ReplenishmentSummaryResponse>(res, "Failed to load replenishment summary");
}

export async function executePlanRun(payload: PlanRequest = {}): Promise<PlanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/planning/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<PlanResponse>(res, "Optimization planning run failed");
}

export async function fetchPlanningRuns(limit = 20, offset = 0): Promise<PlanningRunListResponse> {
  const res = await fetch(`${API_BASE}/api/v1/planning/runs?limit=${limit}&offset=${offset}`, {
    cache: "no-store",
  });
  return handleResponse<PlanningRunListResponse>(res, "Failed to load planning runs history");
}

export async function fetchPlanningRunByCode(runCode: string): Promise<PlanResponse> {
  const res = await fetch(`${API_BASE}/api/v1/planning/runs/${encodeURIComponent(runCode)}`, {
    cache: "no-store",
  });
  return handleResponse<PlanResponse>(res, `Failed to load planning run ${runCode}`);
}
