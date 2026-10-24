"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchInventoryOverview,
  fetchReplenishmentSummary,
  fetchPlanningRuns,
  Warehouse,
} from "@/lib/api";
import {
  Warehouse as WarehouseIcon,
  Store,
  Box,
  Layers,
  Lock,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
  ArrowRight,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { TabType } from "./Navbar";

interface OverviewTabProps {
  onNavigateTab: (tab: TabType) => void;
}

export function OverviewTab({ onNavigateTab }: OverviewTabProps) {
  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useQuery({
    queryKey: ["inventory-overview"],
    queryFn: fetchInventoryOverview,
  });

  const {
    data: replenishment,
    isLoading: replLoading,
    error: replError,
  } = useQuery({
    queryKey: ["replenishment-summary-overview"],
    queryFn: () => fetchReplenishmentSummary({ limit: 1 }),
  });

  const {
    data: historyRuns,
    isLoading: runsLoading,
  } = useQuery({
    queryKey: ["planning-runs-recent"],
    queryFn: () => fetchPlanningRuns(5, 0),
  });

  if (overviewLoading || replLoading) {
    return (
      <div className="space-y-6 animate-pulse" data-testid="overview-loading">
        <div className="h-8 bg-slate-800/60 rounded w-1/3"></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-slate-900 border border-slate-800 rounded-xl"></div>
          ))}
        </div>
        <div className="h-64 bg-slate-900 border border-slate-800 rounded-xl"></div>
      </div>
    );
  }

  if (overviewError) {
    return (
      <div className="rounded-xl border border-rose-800/50 bg-rose-950/20 p-6 text-center space-y-3" data-testid="overview-error">
        <AlertCircle className="h-8 w-8 text-rose-400 mx-auto" />
        <h3 className="text-base font-semibold text-white">Failed to connect to StockWise backend</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          Ensure FastAPI backend is running locally at configured URL. ({overviewError instanceof Error ? overviewError.message : "Error"})
        </p>
        <button
          onClick={() => refetchOverview()}
          className="inline-flex items-center space-x-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-md border border-slate-700"
        >
          <RefreshCw className="h-3 w-3" />
          <span>Retry Connection</span>
        </button>
      </div>
    );
  }

  const chartData = overview?.warehouses.map((w: Warehouse) => ({
    name: w.code,
    fullName: w.name,
    capacity: w.capacity_units,
    city: w.city,
  })) || [];

  const latestRun = historyRuns?.runs && historyRuns.runs.length > 0 ? historyRuns.runs[0] : null;

  return (
    <div className="space-y-6" data-testid="overview-content">
      {/* Page Title & Scope */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white">Distribution Intelligence Overview</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time multi-echelon network status, inventory accounting, and replenishment health
          </p>
        </div>
        <div className="flex items-center space-x-2 text-xs bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg">
          <span className="text-slate-400">Active Dataset:</span>
          <span className="font-mono text-sky-400 font-semibold">{overview?.dataset_version || "Simulated FMCG v1.0"}</span>
        </div>
      </div>

      {/* Network Scope KPIs */}
      <div>
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Network Infrastructure</div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Regional Warehouses</span>
              <WarehouseIcon className="h-4 w-4 text-sky-400" />
            </div>
            <div className="text-2xl font-bold text-white mt-2 font-mono">
              {overview?.total_warehouses ?? 0}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Active distribution centers</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Retail Destinations</span>
              <Store className="h-4 w-4 text-indigo-400" />
            </div>
            <div className="text-2xl font-bold text-white mt-2 font-mono">
              {overview?.total_destinations ?? 0}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Supermarket &amp; grocery stores</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Catalog SKUs</span>
              <Box className="h-4 w-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-white mt-2 font-mono">
              {overview?.total_products ?? 0}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">FMCG packaged goods products</p>
          </div>
        </div>
      </div>

      {/* Inventory Accounting KPIs */}
      <div>
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
          Inventory Accounting (Units)
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Total Physical On-Hand</span>
              <Layers className="h-4 w-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold text-white mt-2 font-mono">
              {(overview?.total_units_on_hand ?? 0).toLocaleString()}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">All batches in warehouse storage</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Reserved Units</span>
              <Lock className="h-4 w-4 text-amber-400" />
            </div>
            <div className="text-2xl font-bold text-amber-400 mt-2 font-mono">
              {(overview?.total_units_reserved ?? 0).toLocaleString()}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Committed to existing orders</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Available Units</span>
              <CheckCircle2 className="h-4 w-4 text-sky-400" />
            </div>
            <div className="text-2xl font-bold text-sky-400 mt-2 font-mono">
              {(overview?.total_units_available ?? 0).toLocaleString()}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">On-hand minus reserved</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Usable Inventory</span>
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-emerald-400 mt-2 font-mono">
              {(overview?.total_units_usable ?? 0).toLocaleString()}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Excludes expired &amp; quarantined</p>
          </div>
        </div>
      </div>

      {/* Network Health & Recent Optimization Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Replenishment Demand Health */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Replenishment &amp; Stockout Risk</h3>
              <span className="text-xs bg-rose-500/10 text-rose-400 border border-rose-500/20 px-2 py-0.5 rounded-full font-mono">
                {replenishment?.critical_count ?? 0} Critical
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Safety-stock replenishment engine alerts across 50 destinations
            </p>

            <div className="grid grid-cols-3 gap-3 my-4">
              <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
                <div className="text-xs text-slate-400">Critical Pairs</div>
                <div className="text-xl font-bold text-rose-400 font-mono mt-1">
                  {replenishment?.critical_count ?? 0}
                </div>
              </div>
              <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
                <div className="text-xs text-slate-400">High Risk</div>
                <div className="text-xl font-bold text-amber-400 font-mono mt-1">
                  {replenishment?.high_count ?? 0}
                </div>
              </div>
              <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
                <div className="text-xs text-slate-400">Demand Units</div>
                <div className="text-xl font-bold text-sky-400 font-mono mt-1">
                  {(replenishment?.total_replenishment_units ?? 0).toLocaleString()}
                </div>
              </div>
            </div>

            <p className="text-[11px] text-slate-500 leading-relaxed">
              * GAP-1 &amp; GAP-2 disclosure: Store on-hand inventory and in-transit dispatches are modeled as 0.
            </p>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-800/80 flex justify-end">
            <button
              onClick={() => onNavigateTab("replenishment")}
              className="inline-flex items-center space-x-1.5 text-xs text-sky-400 hover:text-sky-300 font-medium"
            >
              <span>Inspect Replenishment Requirements</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Latest Planning Run Status */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Latest Optimization Run</h3>
              {latestRun ? (
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-mono ${
                    latestRun.solver_status === "OPTIMAL"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                  }`}
                >
                  {latestRun.solver_status}
                </span>
              ) : (
                <span className="text-xs text-slate-500">No runs yet</span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              OR-Tools distribution MIP solver allocation
            </p>

            {latestRun ? (
              <div className="space-y-2 mt-4 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Run Code:</span>
                  <span className="font-mono text-white">{latestRun.run_code}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Shipped Units:</span>
                  <span className="font-mono text-white font-semibold">
                    {latestRun.total_shipped_units.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Total Freight Cost:</span>
                  <span className="font-mono text-emerald-400 font-semibold">
                    ${latestRun.total_transport_cost.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Created At:</span>
                  <span className="text-slate-300">
                    {new Date(latestRun.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-slate-500">
                Run an optimization to generate multi-echelon shipment recommendations.
              </div>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between">
            <button
              onClick={() => onNavigateTab("history")}
              className="text-xs text-slate-400 hover:text-slate-300"
            >
              View All Runs
            </button>
            <button
              onClick={() => onNavigateTab("optimization")}
              className="inline-flex items-center space-x-1.5 text-xs text-sky-400 hover:text-sky-300 font-medium"
            >
              <span>Launch Optimizer</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Warehouse Hub Capacity Chart */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-white">Warehouse Storage Capacities</h3>
            <p className="text-xs text-slate-400">Daily physical capacity across regional distribution centers</p>
          </div>
          <span className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">
            {chartData.length} Hubs
          </span>
        </div>

        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
              <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
              <YAxis stroke="#64748b" fontSize={11} tickLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#020617",
                  borderColor: "#1e293b",
                  borderRadius: "8px",
                  fontSize: "12px",
                  color: "#f8fafc",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
              <Bar dataKey="capacity" name="Max Capacity (Units)" fill="#38bdf8" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
