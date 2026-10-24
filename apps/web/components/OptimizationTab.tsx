"use client";

import React, { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  executePlanRun,
  PlanRequest,
  PlanResponse,
  Shipment,
} from "@/lib/api";
import { generateShipmentsCSV, downloadCSV } from "@/lib/export";
import {
  Cpu,
  Play,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Download,
  Search,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  ShieldAlert,
  Info,
  Sliders,
} from "lucide-react";

interface OptimizationTabProps {
  currentPlan: PlanResponse | null;
  onPlanGenerated: (plan: PlanResponse) => void;
}

export function OptimizationTab({ currentPlan, onPlanGenerated }: OptimizationTabProps) {
  const [profile, setProfile] = useState<"balanced" | "service_first" | "cost_first">("balanced");
  const [horizonDays, setHorizonDays] = useState<number>(7);
  const [maxLeadTime, setMaxLeadTime] = useState<number | null>(null);
  const [minFulfillmentRate, setMinFulfillmentRate] = useState<number>(0.80);
  const [allowUnconstrainedCostFirst, setAllowUnconstrainedCostFirst] = useState<boolean>(false);
  const [maxSolverTime, setMaxSolverTime] = useState<number>(10);
  const [useReplenishmentEngine, setUseReplenishmentEngine] = useState<boolean>(true);

  const [activeResultsSubTab, setActiveResultsSubTab] = useState<"shipments" | "unmet" | "verification" | "baseline">("shipments");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [page, setPage] = useState<number>(0);
  const pageSize = 15;

  const planMutation = useMutation({
    mutationFn: (payload: PlanRequest) => executePlanRun(payload),
    onSuccess: (data) => {
      onPlanGenerated(data);
      setPage(0);
    },
  });

  const handleRunOptimizer = (e: React.FormEvent) => {
    e.preventDefault();
    if (planMutation.isPending) return;

    const payload: PlanRequest = {
      forecast_horizon_days: horizonDays,
      optimization_profile: profile,
      max_lead_time_days: maxLeadTime,
      min_fulfillment_rate: profile === "cost_first" ? (allowUnconstrainedCostFirst ? 0.0 : minFulfillmentRate) : minFulfillmentRate,
      allow_unconstrained_cost_first: allowUnconstrainedCostFirst,
      parameters: {
        profile: profile,
        max_solver_time_seconds: maxSolverTime,
        use_replenishment_engine: useReplenishmentEngine,
        min_fulfillment_rate: profile === "cost_first" ? (allowUnconstrainedCostFirst ? 0.0 : minFulfillmentRate) : minFulfillmentRate,
        allow_unconstrained_cost_first: allowUnconstrainedCostFirst,
        max_lead_time_days: maxLeadTime,
        lead_time_penalty_weight: 0.20,
      },
    };

    planMutation.mutate(payload);
  };

  const handleExportCSV = () => {
    if (!currentPlan) return;
    const csvData = generateShipmentsCSV(currentPlan);
    downloadCSV(`stockwise_shipments_${currentPlan.run_code}.csv`, csvData);
  };

  const shipments = currentPlan?.shipments || [];
  const filteredShipments = shipments.filter((s: Shipment) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      s.product_name.toLowerCase().includes(term) ||
      s.product_sku.toLowerCase().includes(term) ||
      s.destination_name.toLowerCase().includes(term) ||
      s.destination_code.toLowerCase().includes(term) ||
      s.source_warehouse_code.toLowerCase().includes(term)
    );
  });

  const totalPages = Math.ceil(filteredShipments.length / pageSize);
  const paginatedShipments = filteredShipments.slice(page * pageSize, (page + 1) * pageSize);

  const isFailedSolver =
    currentPlan &&
    (currentPlan.solver_status === "INFEASIBLE" ||
      currentPlan.solver_status === "TARGET_UNACHIEVABLE" ||
      currentPlan.solver_status === "TIMEOUT");

  return (
    <div className="space-y-6" data-testid="optimization-tab">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white">OR-Tools Distribution Optimizer</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Mixed-integer linear programming (MIP) with multi-objective trade-offs and FEFO shelf-life constraints
        </p>
      </div>

      {/* Configuration Form */}
      <form onSubmit={handleRunOptimizer} className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-4 shadow-sm">
        <div className="flex items-center space-x-2 text-xs font-semibold text-white">
          <Sliders className="h-4 w-4 text-sky-400" />
          <span>Solver Formulation &amp; Profile Controls</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Profile */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Optimization Profile</label>
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value as any)}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500 font-medium"
            >
              <option value="balanced">Balanced (Freight + Freshness + Penalties)</option>
              <option value="service_first">Service-First (Lexicographic Stage 1 &amp; 2)</option>
              <option value="cost_first">Cost-First (Minimum Cost with Fulfillment Floor)</option>
            </select>
            <p className="text-[10px] text-slate-500 mt-1">
              {profile === "balanced" && "Penalizes transit lead time ($0.20/d/u) and lost sales."}
              {profile === "service_first" && "Strictly minimizes unmet demand before optimizing freight."}
              {profile === "cost_first" && "Minimizes freight subject to configurable fulfillment rate floor."}
            </p>
          </div>

          {/* Horizon */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Planning Horizon</label>
            <select
              value={horizonDays}
              onChange={(e) => setHorizonDays(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value={3}>3 Days</option>
              <option value={7}>7 Days (Default Standard)</option>
              <option value={14}>14 Days</option>
              <option value={30}>30 Days</option>
            </select>
          </div>

          {/* Delivery Cutoff */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Max Delivery Lead Time</label>
            <select
              value={maxLeadTime ?? ""}
              onChange={(e) => setMaxLeadTime(e.target.value ? Number(e.target.value) : null)}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">No Cutoff (All active routes)</option>
              <option value={2}>2.0 Days Max</option>
              <option value={3}>3.0 Days Max</option>
              <option value={5}>5.0 Days Max</option>
            </select>
            <p className="text-[10px] text-slate-500 mt-1">Excludes long-haul transit corridors</p>
          </div>

          {/* Time Limit */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Solver Time Limit</label>
            <select
              value={maxSolverTime}
              onChange={(e) => setMaxSolverTime(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value={5}>5 Seconds</option>
              <option value={10}>10 Seconds (Standard)</option>
              <option value={30}>30 Seconds</option>
            </select>
          </div>
        </div>

        {/* Cost-First Floor & Switches */}
        <div className="flex flex-wrap items-center gap-6 pt-2 border-t border-slate-800/80 text-xs">
          {profile === "cost_first" && (
            <div className="flex items-center space-x-3 bg-slate-950 p-2 rounded-lg border border-slate-800">
              <span className="text-slate-400">Min Fulfillment Floor:</span>
              <input
                type="range"
                min="0.50"
                max="1.00"
                step="0.05"
                disabled={allowUnconstrainedCostFirst}
                value={minFulfillmentRate}
                onChange={(e) => setMinFulfillmentRate(Number(e.target.value))}
                className="w-28 accent-sky-500 disabled:opacity-30"
              />
              <span className="font-mono text-sky-400 font-bold">
                {allowUnconstrainedCostFirst ? "0% (Unconstrained)" : `${Math.round(minFulfillmentRate * 100)}%`}
              </span>

              <label className="flex items-center space-x-1.5 text-slate-300 ml-3">
                <input
                  type="checkbox"
                  checked={allowUnconstrainedCostFirst}
                  onChange={(e) => setAllowUnconstrainedCostFirst(e.target.checked)}
                  className="rounded border-slate-800 text-sky-600 focus:ring-0"
                />
                <span className="text-[11px]">Unconstrained Opt-In</span>
              </label>
            </div>
          )}

          <label className="flex items-center space-x-2 text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={useReplenishmentEngine}
              onChange={(e) => setUseReplenishmentEngine(e.target.checked)}
              className="rounded border-slate-800 text-sky-600 focus:ring-0"
            />
            <span className="text-xs">Use Replenishment Safety Stock as Demand Signal</span>
          </label>

          <div className="ml-auto">
            <button
              type="submit"
              disabled={planMutation.isPending}
              data-testid="run-optimization-submit-btn"
              className="inline-flex items-center space-x-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50"
            >
              {planMutation.isPending ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  <span>Solving Allocation MIP...</span>
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5 fill-current" />
                  <span>Run Local Optimizer</span>
                </>
              )}
            </button>
          </div>
        </div>
      </form>

      {/* Solver Outcome Card */}
      {currentPlan && (
        <div
          data-testid="solver-outcome-card"
          className={`rounded-xl border p-4 shadow-sm ${
            currentPlan.solver_status === "OPTIMAL"
              ? "bg-emerald-950/20 border-emerald-800/50"
              : isFailedSolver
              ? "bg-rose-950/20 border-rose-800/50"
              : "bg-sky-950/20 border-sky-800/50"
          }`}
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start space-x-3">
              {currentPlan.solver_status === "OPTIMAL" ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
              ) : isFailedSolver ? (
                <XCircle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="flex items-center space-x-2">
                  <h3 className="text-sm font-semibold text-white">
                    Solver Status: <span className="font-mono">{currentPlan.solver_status}</span>
                  </h3>
                  <span className="text-[10px] font-mono uppercase bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded text-slate-300">
                    {currentPlan.optimization_profile || "balanced"}
                  </span>
                </div>
                <p className="text-xs text-slate-300 mt-0.5">
                  {currentPlan.status_message ||
                    (currentPlan.solver_status === "OPTIMAL"
                      ? "Global minimum found satisfying all network constraints and flow conservation."
                      : "Feasible allocation generated within runtime limit.")}
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-3 shrink-0">
              {currentPlan.verification && (
                <div
                  className={`flex items-center space-x-1 px-2.5 py-1 rounded text-xs font-mono border ${
                    currentPlan.verification.is_feasible
                      ? "bg-emerald-950/60 text-emerald-400 border-emerald-800/60"
                      : "bg-rose-950/60 text-rose-400 border-rose-800/60"
                  }`}
                >
                  {currentPlan.verification.is_feasible ? (
                    <ShieldCheck className="h-3.5 w-3.5" />
                  ) : (
                    <ShieldAlert className="h-3.5 w-3.5" />
                  )}
                  <span>{currentPlan.verification.is_feasible ? "Verifier: Feasible" : "Verifier: Violations"}</span>
                </div>
              )}

              <button
                onClick={handleExportCSV}
                className="inline-flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-lg border border-slate-700 transition-colors"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Export CSV</span>
              </button>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 pt-3 border-t border-slate-800/60 text-xs font-mono">
            <div>
              <span className="text-slate-400 text-[11px]">Shipped Units:</span>
              <div className="text-white font-bold text-base mt-0.5">
                {currentPlan.metrics.total_shipped_units.toLocaleString()} u
              </div>
            </div>
            <div>
              <span className="text-slate-400 text-[11px]">Freight Cost:</span>
              <div className="text-emerald-400 font-bold text-base mt-0.5">
                ${currentPlan.metrics.total_transport_cost.toFixed(2)}
              </div>
            </div>
            <div>
              <span className="text-slate-400 text-[11px]">Fulfillment Rate:</span>
              <div className="text-sky-400 font-bold text-base mt-0.5">
                {currentPlan.metrics.fulfillment_rate !== undefined
                  ? `${(currentPlan.metrics.fulfillment_rate * 100).toFixed(1)}%`
                  : "100.0%"}
              </div>
            </div>
            <div>
              <span className="text-slate-400 text-[11px]">Solver Runtime:</span>
              <div className="text-slate-300 font-bold text-base mt-0.5">
                {currentPlan.metrics.solver_runtime_seconds !== undefined
                  ? `${currentPlan.metrics.solver_runtime_seconds.toFixed(2)}s`
                  : "< 1s"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Advisory Notice */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-[11px] text-slate-400 flex items-center space-x-2">
        <Info className="h-4 w-4 text-slate-500 shrink-0" />
        <span>
          <strong>Operational Notice:</strong> Shipment recommendations are planning outputs for inventory allocation. Generating an optimization plan does not dispatch physical stock or modify warehouse inventory balances.
        </span>
      </div>

      {/* Results Sub-Tabs */}
      {currentPlan && (
        <div className="space-y-4">
          <div className="flex space-x-1 border-b border-slate-800 pb-1 text-xs">
            <button
              onClick={() => setActiveResultsSubTab("shipments")}
              className={`px-3 py-1.5 font-medium rounded-md transition-colors ${
                activeResultsSubTab === "shipments"
                  ? "bg-slate-800 text-sky-400 font-semibold"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Shipment Recommendations ({currentPlan.shipments.length})
            </button>
            <button
              onClick={() => setActiveResultsSubTab("unmet")}
              className={`px-3 py-1.5 font-medium rounded-md transition-colors ${
                activeResultsSubTab === "unmet"
                  ? "bg-slate-800 text-sky-400 font-semibold"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Unmet Demand ({currentPlan.unmet_demands?.length || 0})
            </button>
            <button
              onClick={() => setActiveResultsSubTab("verification")}
              className={`px-3 py-1.5 font-medium rounded-md transition-colors ${
                activeResultsSubTab === "verification"
                  ? "bg-slate-800 text-sky-400 font-semibold"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Solution Verifier (12 Invariants)
            </button>
            <button
              onClick={() => setActiveResultsSubTab("baseline")}
              className={`px-3 py-1.5 font-medium rounded-md transition-colors ${
                activeResultsSubTab === "baseline"
                  ? "bg-slate-800 text-sky-400 font-semibold"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Greedy Baseline Delta
            </button>
          </div>

          {/* Sub-Tab 1: Shipments Table */}
          {activeResultsSubTab === "shipments" && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-sm space-y-3 p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-semibold text-white">Recommended Allocation Schedule</span>
                <div className="relative">
                  <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-slate-500" />
                  <input
                    type="text"
                    placeholder="Filter SKU, hub, store..."
                    value={searchTerm}
                    onChange={(e) => {
                      setSearchTerm(e.target.value);
                      setPage(0);
                    }}
                    className="bg-slate-950 border border-slate-800 text-xs rounded-lg pl-8 pr-3 py-1.5 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-sky-500 w-64"
                  />
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 font-medium">
                      <th className="py-2.5 px-3">Product / SKU</th>
                      <th className="py-2.5 px-3">Source Hub</th>
                      <th className="py-2.5 px-3">Destination</th>
                      <th className="py-2.5 px-3 text-right">Units</th>
                      <th className="py-2.5 px-3 text-right">Freight Cost</th>
                      <th className="py-2.5 px-3 text-right">Lead Time</th>
                      <th className="py-2.5 px-3">Allocation Rationale</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {paginatedShipments.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-slate-500">
                          No shipments matching search criteria.
                        </td>
                      </tr>
                    ) : (
                      paginatedShipments.map((s, idx) => (
                        <tr key={`${s.id}-${idx}`} className="hover:bg-slate-800/30 transition-colors">
                          <td className="py-2.5 px-3">
                            <div className="font-medium text-white">{s.product_name}</div>
                            <div className="text-[10px] font-mono text-slate-500">{s.product_sku}</div>
                          </td>
                          <td className="py-2.5 px-3 font-mono font-medium text-sky-400">
                            {s.source_warehouse_code}
                          </td>
                          <td className="py-2.5 px-3">
                            <div className="text-slate-200">{s.destination_name}</div>
                            <div className="text-[10px] font-mono text-slate-500">{s.destination_code}</div>
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono font-semibold text-white">
                            {s.recommended_units.toLocaleString()}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-emerald-400">
                            ${s.total_transport_cost.toFixed(2)}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                            {s.lead_time_days !== undefined ? `${s.lead_time_days.toFixed(1)}d` : "1.0d"}
                          </td>
                          <td className="py-2.5 px-3 max-w-sm text-slate-400 text-[11px] leading-relaxed">
                            {s.reasoning || "Least-cost route fulfilling destination replenishment signal."}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs text-slate-400">
                <div>
                  Showing {paginatedShipments.length} of {filteredShipments.length} shipments (Page {page + 1} of {Math.max(1, totalPages)})
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <span className="font-mono text-xs text-slate-300">{page + 1}</span>
                  <button
                    onClick={() => setPage((p) => (p + 1 < totalPages ? p + 1 : p))}
                    disabled={page + 1 >= totalPages}
                    className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Sub-Tab 2: Unmet Demand */}
          {activeResultsSubTab === "unmet" && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
              <span className="text-xs font-semibold text-white">Unsatisfied Downstream Demand</span>
              <p className="text-xs text-slate-400">
                Corridors where requested replenishment exceeded available warehouse supply or delivery lead-time limits.
              </p>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 font-medium">
                      <th className="py-2.5 px-3">Product</th>
                      <th className="py-2.5 px-3">Destination</th>
                      <th className="py-2.5 px-3 text-right">Demanded</th>
                      <th className="py-2.5 px-3 text-right">Fulfilled</th>
                      <th className="py-2.5 px-3 text-right">Unmet Units</th>
                      <th className="py-2.5 px-3">Risk Level</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {!currentPlan.unmet_demands || currentPlan.unmet_demands.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-emerald-400 font-medium">
                          Zero unmet demand. 100% of network replenishment requirements fulfilled.
                        </td>
                      </tr>
                    ) : (
                      currentPlan.unmet_demands.map((u, i) => (
                        <tr key={i} className="hover:bg-slate-800/30">
                          <td className="py-2 px-3">
                            <span className="font-medium text-white">{u.product_name}</span>
                            <span className="text-[10px] text-slate-500 font-mono ml-1.5">{u.product_sku}</span>
                          </td>
                          <td className="py-2 px-3 text-slate-200">
                            {u.destination_name} ({u.destination_code})
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-slate-300">{u.demanded_units}</td>
                          <td className="py-2 px-3 text-right font-mono text-sky-400">{u.fulfilled_units}</td>
                          <td className="py-2 px-3 text-right font-mono font-bold text-rose-400">{u.unmet_units}</td>
                          <td className="py-2 px-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-950 text-rose-400 border border-rose-800">
                              {u.risk_category}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Sub-Tab 3: Verification Audit */}
          {activeResultsSubTab === "verification" && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Independent Solution Verifier</h3>
                  <p className="text-xs text-slate-400">
                    Empirical verification of 12 mathematical invariants independent of solver internals
                  </p>
                </div>
                <span
                  className={`text-xs px-2.5 py-1 rounded-full font-mono font-bold border ${
                    currentPlan.verification?.is_feasible
                      ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                      : "bg-rose-950 text-rose-400 border-rose-800"
                  }`}
                >
                  {currentPlan.verification?.is_feasible ? "ALL INVARIANTS SATISFIED" : "FEASIBILITY VIOLATIONS DETECTED"}
                </span>
              </div>

              {currentPlan.verification && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                  <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                    <span className="text-slate-400">Recalculated Units:</span>
                    <div className="text-white font-bold mt-1">{currentPlan.verification.recalculated_units.toLocaleString()}</div>
                  </div>
                  <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                    <span className="text-slate-400">Recalculated Cost:</span>
                    <div className="text-emerald-400 font-bold mt-1">${currentPlan.verification.recalculated_cost.toFixed(2)}</div>
                  </div>
                  <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                    <span className="text-slate-400">Fulfilled vs Demanded:</span>
                    <div className="text-sky-400 font-bold mt-1">
                      {currentPlan.verification.recalculated_fulfilled} / {currentPlan.metrics.total_demanded_units ?? currentPlan.verification.recalculated_fulfilled}
                    </div>
                  </div>
                  <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                    <span className="text-slate-400">Violations Count:</span>
                    <div className={`font-bold mt-1 ${currentPlan.verification.violations_count === 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {currentPlan.verification.violations_count}
                    </div>
                  </div>
                </div>
              )}

              {currentPlan.verification?.violations && currentPlan.verification.violations.length > 0 && (
                <div className="p-3 bg-rose-950/40 border border-rose-800 rounded-lg text-xs text-rose-300 space-y-1">
                  <div className="font-semibold">Constraint Violations:</div>
                  {currentPlan.verification.violations.map((v, i) => (
                    <div key={i}>&bull; {v}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Sub-Tab 4: Baseline Comparison */}
          {activeResultsSubTab === "baseline" && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Deterministic Greedy Baseline Comparison</h3>
                  <p className="text-xs text-slate-400">
                    Evaluating OR-Tools MIP against a fast greedy shortest-distance baseline
                  </p>
                </div>
              </div>

              {currentPlan.baseline_comparison ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
                  <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                    <span className="text-slate-400 font-sans font-semibold">Greedy Baseline</span>
                    <div className="text-slate-300">Units: {currentPlan.baseline_comparison.baseline_total_units.toLocaleString()}</div>
                    <div className="text-slate-300">Cost: ${currentPlan.baseline_comparison.baseline_total_cost.toFixed(2)}</div>
                    <div className="text-slate-300">
                      Rate: {(currentPlan.baseline_comparison.baseline_fulfillment_rate * 100).toFixed(1)}%
                    </div>
                  </div>

                  <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                    <span className="text-sky-400 font-sans font-semibold">OR-Tools Optimizer</span>
                    <div className="text-white font-bold">Units: {currentPlan.baseline_comparison.optimized_total_units.toLocaleString()}</div>
                    <div className="text-emerald-400 font-bold">Cost: ${currentPlan.baseline_comparison.optimized_total_cost.toFixed(2)}</div>
                    <div className="text-sky-400 font-bold">
                      Rate: {(currentPlan.baseline_comparison.optimized_fulfillment_rate * 100).toFixed(1)}%
                    </div>
                  </div>

                  <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                    <span className="text-amber-400 font-sans font-semibold">Optimization Delta</span>
                    <div className="text-white">
                      Units Delta: {currentPlan.baseline_comparison.units_difference >= 0 ? `+${currentPlan.baseline_comparison.units_difference}` : currentPlan.baseline_comparison.units_difference}
                    </div>
                    <div className={currentPlan.baseline_comparison.cost_difference <= 0 ? "text-emerald-400" : "text-rose-400"}>
                      Cost Delta: {currentPlan.baseline_comparison.cost_difference <= 0 ? `-$${Math.abs(currentPlan.baseline_comparison.cost_difference).toFixed(2)}` : `+$${currentPlan.baseline_comparison.cost_difference.toFixed(2)}`}
                    </div>
                    <div className="text-sky-400">
                      Rate Delta: {(currentPlan.baseline_comparison.fulfillment_rate_difference * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-xs text-slate-500">
                  Greedy baseline comparison data unavailable for this run.
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
