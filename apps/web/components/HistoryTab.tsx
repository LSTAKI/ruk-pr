"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchPlanningRuns,
  fetchPlanningRunByCode,
  PlanningRunListItem,
  PlanResponse,
} from "@/lib/api";
import { generateShipmentsCSV, downloadCSV } from "@/lib/export";
import {
  History,
  Clock,
  Eye,
  Download,
  X,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

interface HistoryTabProps {
  onLoadRunToDashboard?: (plan: PlanResponse) => void;
}

export function HistoryTab({ onLoadRunToDashboard }: HistoryTabProps) {
  const [page, setPage] = useState<number>(0);
  const [selectedRunCode, setSelectedRunCode] = useState<string | null>(null);
  const pageSize = 15;

  const {
    data: historyData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["planning-history-runs", page],
    queryFn: () => fetchPlanningRuns(pageSize, page * pageSize),
  });

  const {
    data: runDetail,
    isLoading: detailLoading,
  } = useQuery({
    queryKey: ["planning-run-detail", selectedRunCode],
    queryFn: () => (selectedRunCode ? fetchPlanningRunByCode(selectedRunCode) : null),
    enabled: !!selectedRunCode,
  });

  const runs = historyData?.runs || [];
  const total = historyData?.total || 0;
  const totalPages = Math.ceil(total / pageSize);

  const handleExportCSV = (plan: PlanResponse) => {
    const csv = generateShipmentsCSV(plan);
    downloadCSV(`stockwise_plan_${plan.run_code}.csv`, csv);
  };

  return (
    <div className="space-y-6" data-testid="planning-history-tab">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white">Planning Runs History &amp; Audit Log</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Persisted record of distribution MIP optimization executions, solver statuses, and shipment schedules
        </p>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-medium">
                <th className="py-3 px-3">Run Code</th>
                <th className="py-3 px-3">Created At</th>
                <th className="py-3 px-3">Forecast Identifier</th>
                <th className="py-3 px-3">Solver Status</th>
                <th className="py-3 px-3 text-right">Shipped Units</th>
                <th className="py-3 px-3 text-right">Freight Cost</th>
                <th className="py-3 px-3 text-right">Stockout Risks</th>
                <th className="py-3 px-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400 animate-pulse">
                    Loading historical optimization runs...
                  </td>
                </tr>
              ) : isError ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-rose-400">
                    Failed to load history: {error instanceof Error ? error.message : "Error"}
                  </td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    No planning runs have been executed yet. Run the local optimizer to create a run record.
                  </td>
                </tr>
              ) : (
                runs.map((r: PlanningRunListItem) => (
                  <tr key={r.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3 font-mono font-bold text-white">{r.run_code}</td>
                    <td className="py-2.5 px-3 text-slate-400">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-slate-300">{r.forecast_identifier}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                          r.solver_status === "OPTIMAL"
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                            : "bg-amber-950 text-amber-400 border border-amber-800"
                        }`}
                      >
                        {r.solver_status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-white font-semibold">
                      {r.total_shipped_units.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-emerald-400 font-semibold">
                      ${r.total_transport_cost.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {r.stockout_risk_count}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <button
                        onClick={() => setSelectedRunCode(r.run_code)}
                        className="inline-flex items-center space-x-1 text-xs text-sky-400 hover:text-sky-300 underline font-medium"
                      >
                        <Eye className="h-3 w-3" />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800 text-xs text-slate-400">
          <div>
            Showing {runs.length} of {total} runs (Page {page + 1} of {Math.max(1, totalPages)})
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

      {/* Detail Modal */}
      {selectedRunCode && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white">Historical Plan Inspection</h3>
                <p className="text-xs text-slate-400 font-mono">Run: {selectedRunCode}</p>
              </div>
              <button
                onClick={() => setSelectedRunCode(null)}
                className="text-slate-400 hover:text-white p-1 rounded"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto space-y-4 text-xs">
              {detailLoading ? (
                <div className="py-12 text-center text-slate-400 animate-pulse">
                  Loading plan details from SQLite database...
                </div>
              ) : runDetail ? (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <span className="text-slate-400 text-[11px]">Solver Status:</span>
                      <div className="text-white font-bold text-sm mt-0.5">{runDetail.solver_status}</div>
                    </div>
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <span className="text-slate-400 text-[11px]">Shipped Units:</span>
                      <div className="text-sky-400 font-bold text-sm mt-0.5">
                        {runDetail.metrics.total_shipped_units.toLocaleString()}
                      </div>
                    </div>
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <span className="text-slate-400 text-[11px]">Freight Cost:</span>
                      <div className="text-emerald-400 font-bold text-sm mt-0.5">
                        ${runDetail.metrics.total_transport_cost.toFixed(2)}
                      </div>
                    </div>
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                      <span className="text-slate-400 text-[11px]">Fulfillment Rate:</span>
                      <div className="text-white font-bold text-sm mt-0.5">
                        {runDetail.metrics.fulfillment_rate !== undefined
                          ? `${(runDetail.metrics.fulfillment_rate * 100).toFixed(1)}%`
                          : "100%"}
                      </div>
                    </div>
                  </div>

                  {/* Recommendations */}
                  <div>
                    <h4 className="font-semibold text-slate-200 mb-2">
                      Shipment Recommendations ({runDetail.shipments.length})
                    </h4>
                    <div className="max-h-60 overflow-y-auto border border-slate-800 rounded-lg">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 sticky top-0 text-slate-400 border-b border-slate-800">
                          <tr>
                            <th className="py-2 px-2.5">SKU / Product</th>
                            <th className="py-2 px-2.5">Origin Hub</th>
                            <th className="py-2 px-2.5">Destination</th>
                            <th className="py-2 px-2.5 text-right">Units</th>
                            <th className="py-2 px-2.5 text-right">Cost ($)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/40">
                          {runDetail.shipments.map((s, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/20 font-mono">
                              <td className="py-1.5 px-2.5 font-sans text-slate-300">
                                {s.product_name} ({s.product_sku})
                              </td>
                              <td className="py-1.5 px-2.5 text-sky-400">{s.source_warehouse_code}</td>
                              <td className="py-1.5 px-2.5 font-sans text-slate-300">
                                {s.destination_name} ({s.destination_code})
                              </td>
                              <td className="py-1.5 px-2.5 text-right text-white font-semibold">
                                {s.recommended_units}
                              </td>
                              <td className="py-1.5 px-2.5 text-right text-emerald-400">
                                ${s.total_transport_cost.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              ) : (
                <div className="py-12 text-center text-rose-400">
                  Run details could not be retrieved.
                </div>
              )}
            </div>

            <div className="p-3 border-t border-slate-800 bg-slate-950 flex items-center justify-between">
              {runDetail ? (
                <button
                  onClick={() => handleExportCSV(runDetail)}
                  className="inline-flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-lg border border-slate-700"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>Download Run CSV</span>
                </button>
              ) : (
                <div></div>
              )}

              <button
                onClick={() => setSelectedRunCode(null)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-4 py-1.5 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
