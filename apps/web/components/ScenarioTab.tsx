"use client";

import React, { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { executePlanRun, PlanResponse } from "@/lib/api";
import {
  GitCompare,
  Play,
  RefreshCw,
  Info,
  CheckCircle2,
  XCircle,
  TrendingDown,
  TrendingUp,
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

export function ScenarioTab() {
  const [horizonDays, setHorizonDays] = useState<number>(7);
  const [minCostFirstFulfillment, setMinCostFirstFulfillment] = useState<number>(0.80);
  const [results, setResults] = useState<{
    costFirst?: PlanResponse;
    serviceFirst?: PlanResponse;
    balanced?: PlanResponse;
  }>({});

  const comparisonMutation = useMutation({
    mutationFn: async () => {
      // Execute all 3 profiles on identical inputs
      const [costRes, servRes, balRes] = await Promise.all([
        executePlanRun({
          forecast_horizon_days: horizonDays,
          optimization_profile: "cost_first",
          min_fulfillment_rate: minCostFirstFulfillment,
          parameters: {
            profile: "cost_first",
            min_fulfillment_rate: minCostFirstFulfillment,
            max_solver_time_seconds: 10,
            use_replenishment_engine: true,
          },
        }),
        executePlanRun({
          forecast_horizon_days: horizonDays,
          optimization_profile: "service_first",
          parameters: {
            profile: "service_first",
            max_solver_time_seconds: 10,
            use_replenishment_engine: true,
          },
        }),
        executePlanRun({
          forecast_horizon_days: horizonDays,
          optimization_profile: "balanced",
          parameters: {
            profile: "balanced",
            lead_time_penalty_weight: 0.20,
            max_solver_time_seconds: 10,
            use_replenishment_engine: true,
          },
        }),
      ]);

      return {
        costFirst: costRes,
        serviceFirst: servRes,
        balanced: balRes,
      };
    },
    onSuccess: (data) => {
      setResults(data);
    },
  });

  const { costFirst, serviceFirst, balanced } = results;
  const hasResults = !!(costFirst && serviceFirst && balanced);

  const chartData = hasResults
    ? [
        {
          name: "Cost-First",
          fulfillmentRate: Number(((costFirst.metrics.fulfillment_rate ?? 0) * 100).toFixed(1)),
          cost: Number(costFirst.metrics.total_transport_cost.toFixed(2)),
          units: costFirst.metrics.total_shipped_units,
        },
        {
          name: "Balanced",
          fulfillmentRate: Number(((balanced.metrics.fulfillment_rate ?? 0) * 100).toFixed(1)),
          cost: Number(balanced.metrics.total_transport_cost.toFixed(2)),
          units: balanced.metrics.total_shipped_units,
        },
        {
          name: "Service-First",
          fulfillmentRate: Number(((serviceFirst.metrics.fulfillment_rate ?? 0) * 100).toFixed(1)),
          cost: Number(serviceFirst.metrics.total_transport_cost.toFixed(2)),
          units: serviceFirst.metrics.total_shipped_units,
        },
      ]
    : [];

  return (
    <div className="space-y-6" data-testid="scenario-comparison-tab">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white">Multi-Profile Scenario Comparison</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Evaluating trade-offs between Cost-First, Service-First, and Balanced optimization objectives under identical network constraints
        </p>
      </div>

      {/* Profile Formulation Explanations */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5">
          <span className="font-semibold text-emerald-400 font-mono">Cost-First Profile</span>
          <p className="text-slate-300 leading-relaxed text-[11px]">
            Minimizes pure transportation freight costs. Subject to a mandatory network fulfillment rate floor (default &ge; 80%) to prevent zero-fulfillment pathological minimizers.
          </p>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5">
          <span className="font-semibold text-sky-400 font-mono">Service-First Profile</span>
          <p className="text-slate-300 leading-relaxed text-[11px]">
            Strict lexicographic 2-stage optimization: Stage 1 minimizes total unmet demand units. Stage 2 minimizes freight cost without conceding a single fulfilled unit.
          </p>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-1.5">
          <span className="font-semibold text-indigo-400 font-mono">Balanced Profile</span>
          <p className="text-slate-300 leading-relaxed text-[11px]">
            Combined objective function minimizing freight cost + transit lead time freshness penalty ($0.20/day/unit) + lost sales stockout penalty ($5.00/unit).
          </p>
        </div>
      </div>

      {/* Execution Form */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Planning Horizon</label>
            <select
              value={horizonDays}
              onChange={(e) => setHorizonDays(Number(e.target.value))}
              className="bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value={7}>7 Days (Standard)</option>
              <option value={14}>14 Days</option>
              <option value={30}>30 Days</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Cost-First Min Fulfillment Floor</label>
            <div className="flex items-center space-x-2">
              <input
                type="range"
                min="0.50"
                max="1.00"
                step="0.05"
                value={minCostFirstFulfillment}
                onChange={(e) => setMinCostFirstFulfillment(Number(e.target.value))}
                className="w-28 accent-sky-500"
              />
              <span className="font-mono text-xs text-sky-400 font-bold">
                {Math.round(minCostFirstFulfillment * 100)}%
              </span>
            </div>
          </div>
        </div>

        <button
          onClick={() => comparisonMutation.mutate()}
          disabled={comparisonMutation.isPending}
          data-testid="run-scenario-comparison-btn"
          className="inline-flex items-center space-x-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50"
        >
          {comparisonMutation.isPending ? (
            <>
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              <span>Solving All 3 Profiles...</span>
            </>
          ) : (
            <>
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>Run Scenario Comparison</span>
            </>
          )}
        </button>
      </div>

      {/* Comparison Matrix Table */}
      {hasResults && (
        <div className="space-y-6" data-testid="scenario-results">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-sm">
            <div className="p-4 border-b border-slate-800">
              <h3 className="text-sm font-semibold text-white">Profile Comparison Matrix (Identical Corridors &amp; Demand)</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-medium">
                    <th className="py-3 px-3">Metric</th>
                    <th className="py-3 px-3 text-right text-emerald-400">Cost-First</th>
                    <th className="py-3 px-3 text-right text-indigo-400">Balanced</th>
                    <th className="py-3 px-3 text-right text-sky-400">Service-First</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">Solver Status</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400">{costFirst.solver_status}</td>
                    <td className="py-2.5 px-3 text-right text-indigo-400">{balanced.solver_status}</td>
                    <td className="py-2.5 px-3 text-right text-sky-400">{serviceFirst.solver_status}</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">Total Shipped Units</td>
                    <td className="py-2.5 px-3 text-right text-white font-bold">
                      {costFirst.metrics.total_shipped_units.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right text-white font-bold">
                      {balanced.metrics.total_shipped_units.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right text-white font-bold">
                      {serviceFirst.metrics.total_shipped_units.toLocaleString()}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">Unmet Demand Units</td>
                    <td className="py-2.5 px-3 text-right text-rose-400">
                      {(costFirst.metrics.total_unmet_units ?? 0).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right text-slate-300">
                      {(balanced.metrics.total_unmet_units ?? 0).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right text-sky-400">
                      {(serviceFirst.metrics.total_unmet_units ?? 0).toLocaleString()}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">Network Fulfillment Rate</td>
                    <td className="py-2.5 px-3 text-right text-white">
                      {((costFirst.metrics.fulfillment_rate ?? 0) * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 text-right text-white">
                      {((balanced.metrics.fulfillment_rate ?? 0) * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 text-right text-white">
                      {((serviceFirst.metrics.fulfillment_rate ?? 0) * 100).toFixed(1)}%
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">Total Freight Cost</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400 font-bold">
                      ${costFirst.metrics.total_transport_cost.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-right text-indigo-400 font-bold">
                      ${balanced.metrics.total_transport_cost.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-right text-sky-400 font-bold">
                      ${serviceFirst.metrics.total_transport_cost.toFixed(2)}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">Average Freight / Unit</td>
                    <td className="py-2.5 px-3 text-right text-slate-300">
                      ${(costFirst.metrics.total_transport_cost / Math.max(1, costFirst.metrics.total_shipped_units)).toFixed(3)}
                    </td>
                    <td className="py-2.5 px-3 text-right text-slate-300">
                      ${(balanced.metrics.total_transport_cost / Math.max(1, balanced.metrics.total_shipped_units)).toFixed(3)}
                    </td>
                    <td className="py-2.5 px-3 text-right text-slate-300">
                      ${(serviceFirst.metrics.total_transport_cost / Math.max(1, serviceFirst.metrics.total_shipped_units)).toFixed(3)}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">Expiry Metric Status</td>
                    <td className="py-2.5 px-3 text-right text-slate-500 font-sans">Not Modeled</td>
                    <td className="py-2.5 px-3 text-right text-slate-500 font-sans">Not Modeled</td>
                    <td className="py-2.5 px-3 text-right text-slate-500 font-sans">Not Modeled</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-sans font-medium text-slate-300">12-Invariant Verification</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400 font-sans">
                      {costFirst.verification?.is_feasible ? "FEASIBLE" : "VIOLATIONS"}
                    </td>
                    <td className="py-2.5 px-3 text-right text-emerald-400 font-sans">
                      {balanced.verification?.is_feasible ? "FEASIBLE" : "VIOLATIONS"}
                    </td>
                    <td className="py-2.5 px-3 text-right text-emerald-400 font-sans">
                      {serviceFirst.verification?.is_feasible ? "FEASIBLE" : "VIOLATIONS"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Trade-off Analysis Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-2 text-xs">
              <div className="flex items-center space-x-2 text-sky-400 font-semibold">
                <TrendingUp className="h-4 w-4" />
                <span>Service Premium (Service-First vs Cost-First)</span>
              </div>
              <p className="text-slate-300 text-[11px] leading-relaxed">
                Service-First fulfills{" "}
                <strong className="text-white">
                  {(serviceFirst.metrics.total_shipped_units - costFirst.metrics.total_shipped_units).toLocaleString()} additional units
                </strong>{" "}
                at an incremental freight investment of{" "}
                <strong className="text-emerald-400">
                  +${Math.max(0, serviceFirst.metrics.total_transport_cost - costFirst.metrics.total_transport_cost).toFixed(2)}
                </strong>.
              </p>
            </div>

            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-2 text-xs">
              <div className="flex items-center space-x-2 text-indigo-400 font-semibold">
                <TrendingDown className="h-4 w-4" />
                <span>Balanced Profile Trade-off</span>
              </div>
              <p className="text-slate-300 text-[11px] leading-relaxed">
                Balanced profile incorporates the transit penalty ($0.20/day/unit), favoring faster delivery routes to preserve product shelf life.
              </p>
            </div>
          </div>

          {/* Visual Chart */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <h3 className="text-sm font-semibold text-white mb-4">Total Freight Cost Across Profiles ($)</h3>
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
                  <Bar dataKey="cost" name="Freight Cost ($)" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
