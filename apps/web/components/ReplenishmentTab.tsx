"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchReplenishmentSummary,
  fetchProducts,
  fetchDestinations,
  ReplenishmentRequirement,
} from "@/lib/api";
import {
  RotateCcw,
  AlertTriangle,
  ShieldAlert,
  Clock,
  Info,
  Search,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  X,
} from "lucide-react";

export function ReplenishmentTab() {
  const [riskFilter, setRiskFilter] = useState<string>("");
  const [productId, setProductId] = useState<number | undefined>(undefined);
  const [destinationId, setDestinationId] = useState<number | undefined>(undefined);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [page, setPage] = useState<number>(0);
  const [selectedItem, setSelectedItem] = useState<ReplenishmentRequirement | null>(null);
  const pageSize = 50;

  const { data: products } = useQuery({
    queryKey: ["inventory-products"],
    queryFn: fetchProducts,
  });

  const { data: destinations } = useQuery({
    queryKey: ["inventory-destinations"],
    queryFn: fetchDestinations,
  });

  const {
    data: replData,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["replenishment-summary", riskFilter, productId, destinationId, page],
    queryFn: () =>
      fetchReplenishmentSummary({
        product_id: productId,
        destination_id: destinationId,
        risk_filter: riskFilter || undefined,
        limit: pageSize,
        offset: page * pageSize,
      }),
  });

  const items = replData?.requirements || [];
  const total = replData?.total || 0;
  const totalPages = Math.ceil(total / pageSize);

  const filtered = items.filter((req) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      req.product_sku.toLowerCase().includes(term) ||
      req.product_name.toLowerCase().includes(term) ||
      req.destination_code.toLowerCase().includes(term) ||
      req.destination_name.toLowerCase().includes(term)
    );
  });

  const getRiskBadge = (category: string) => {
    switch (category) {
      case "Critical":
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-rose-950/80 text-rose-400 border border-rose-800/80">
            <ShieldAlert className="h-3 w-3" />
            <span>Critical</span>
          </span>
        );
      case "High":
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-amber-950/80 text-amber-400 border border-amber-800/80">
            <AlertTriangle className="h-3 w-3" />
            <span>High</span>
          </span>
        );
      case "Moderate":
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-yellow-950/80 text-yellow-400 border border-yellow-800/80">
            <Clock className="h-3 w-3" />
            <span>Moderate</span>
          </span>
        );
      case "Low":
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-950/80 text-emerald-400 border border-emerald-800/80">
            <span>Low</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-slate-900 text-slate-400 border border-slate-800">
            <span>{category}</span>
          </span>
        );
    }
  };

  return (
    <div className="space-y-6" data-testid="replenishment-planner-tab">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white">Inventory Position &amp; Replenishment Engine</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Safety-stock policies, lead-time demand, reorder thresholds, and downstream replenishment signals
        </p>
      </div>

      {/* Prominent Architectural Limitations Disclosure Banner */}
      <div className="rounded-xl border border-amber-600/60 bg-amber-950/30 p-4 text-xs text-slate-200 space-y-1.5 shadow-sm">
        <div className="flex items-center space-x-2 text-amber-400 font-semibold text-sm">
          <AlertTriangle className="h-4 w-4" />
          <span>Operational Model Notice: Known Data Gaps (GAP-1 &amp; GAP-2)</span>
        </div>
        <p className="leading-relaxed text-slate-300">
          <strong>Destination Store On-Hand Inventory (GAP-1):</strong> Retail destination store stock is currently not recorded in the central database schema and is assumed to be <strong>0 units</strong>.
        </p>
        <p className="leading-relaxed text-slate-300">
          <strong>Committed In-Transit Dispatches (GAP-2):</strong> Confirmed orders currently in transit are not tracked and are assumed to be <strong>0 units</strong>. Consequently, the projected inventory position equals zero, and gross replenishment equals the full threshold (LTD + Safety Stock).
        </p>
      </div>

      {/* Risk Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <span className="text-xs text-slate-400">Critical Risk Pairs</span>
          <div className="text-2xl font-bold text-rose-400 mt-1 font-mono">
            {replData?.critical_count ?? 0}
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Stockout within route lead time</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <span className="text-xs text-slate-400">High Risk Pairs</span>
          <div className="text-2xl font-bold text-amber-400 mt-1 font-mono">
            {replData?.high_count ?? 0}
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Cover &le; 1.5 &times; lead time</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <span className="text-xs text-slate-400">Moderate / Low</span>
          <div className="text-2xl font-bold text-emerald-400 mt-1 font-mono">
            {(replData?.moderate_count ?? 0) + (replData?.low_count ?? 0)}
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Sufficiently buffered pairs</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <span className="text-xs text-slate-400">Total Replenishment Demand</span>
          <div className="text-2xl font-bold text-sky-400 mt-1 font-mono">
            {(replData?.total_replenishment_units ?? 0).toLocaleString()} u
          </div>
          <p className="text-[11px] text-slate-500 mt-1">Optimizer demand contract input</p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* Risk Level */}
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Risk Category Filter</label>
            <select
              value={riskFilter}
              onChange={(e) => {
                setRiskFilter(e.target.value);
                setPage(0);
              }}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">All Risk Tiers</option>
              <option value="Critical">Critical Only</option>
              <option value="High">High &amp; Critical</option>
              <option value="Moderate">Moderate, High, Critical</option>
            </select>
          </div>

          {/* Product Filter */}
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Catalog Product</label>
            <select
              value={productId ?? ""}
              onChange={(e) => {
                setProductId(e.target.value ? Number(e.target.value) : undefined);
                setPage(0);
              }}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">All Products</option>
              {products?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} - {p.name}
                </option>
              ))}
            </select>
          </div>

          {/* Destination Filter */}
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Destination Store</label>
            <select
              value={destinationId ?? ""}
              onChange={(e) => {
                setDestinationId(e.target.value ? Number(e.target.value) : undefined);
                setPage(0);
              }}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">All Destinations</option>
              {destinations?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code} - {d.name}
                </option>
              ))}
            </select>
          </div>

          {/* Search Term */}
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Search Store / SKU</label>
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search SKU, store..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg pl-8 pr-2.5 py-1.5 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Requirements Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-medium">
                <th className="py-3 px-3">Product SKU</th>
                <th className="py-3 px-3">Destination</th>
                <th className="py-3 px-3 text-right">Lead Time</th>
                <th className="py-3 px-3 text-right">Daily Mean</th>
                <th className="py-3 px-3 text-right">LT Demand</th>
                <th className="py-3 px-3 text-right">Safety Stock</th>
                <th className="py-3 px-3 text-right">Reorder Threshold</th>
                <th className="py-3 px-3 text-right">Replenish Qty</th>
                <th className="py-3 px-3">Risk Level</th>
                <th className="py-3 px-3 text-center">Explanation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {isLoading ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-400 animate-pulse">
                    Calculating multi-echelon replenishment requirements...
                  </td>
                </tr>
              ) : isError ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-rose-400">
                    Failed to load replenishment data: {error instanceof Error ? error.message : "Error"}
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500">
                    No replenishment requirements matching current criteria.
                  </td>
                </tr>
              ) : (
                filtered.map((req, idx) => (
                  <tr key={`${req.product_id}-${req.destination_id}-${idx}`} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3">
                      <div className="font-medium text-white">{req.product_name}</div>
                      <div className="text-[10px] font-mono text-slate-500">{req.product_sku}</div>
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="text-slate-200">{req.destination_name}</div>
                      <div className="text-[10px] font-mono text-slate-500">{req.destination_code}</div>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {req.lead_time_days.toFixed(1)}d
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {req.daily_mean_demand.toFixed(1)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {req.lead_time_demand.toFixed(1)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-amber-400 font-medium">
                      {req.safety_stock.safety_stock_int} u
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {req.replenishment_threshold.toFixed(1)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-sky-400">
                      {req.replenishment_qty.toLocaleString()} u
                    </td>
                    <td className="py-2.5 px-3">
                      {getRiskBadge(req.risk_category)}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <button
                        onClick={() => setSelectedItem(req)}
                        className="text-xs text-sky-400 hover:text-sky-300 underline font-medium"
                      >
                        Details
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
            Showing {filtered.length} of {total} requirements (Page {page + 1} of {Math.max(1, totalPages)})
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

      {/* Detail / Explanation Modal */}
      {selectedItem && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-semibold text-white">Replenishment Driver Explanation</h3>
                <p className="text-xs text-slate-400">
                  {selectedItem.product_sku} &rarr; {selectedItem.destination_code}
                </p>
              </div>
              <button
                onClick={() => setSelectedItem(null)}
                className="text-slate-400 hover:text-white p-1 rounded"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="font-semibold text-sky-400">Mathematical Rationale:</span>
                <p className="text-slate-300 leading-relaxed">{selectedItem.explanation}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-500">Route Lead Time:</span>
                  <div className="font-mono text-slate-200 font-semibold">{selectedItem.lead_time_days} days</div>
                </div>
                <div className="p-2 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-500">Safety Stock Method:</span>
                  <div className="font-mono text-slate-200 font-semibold uppercase">{selectedItem.safety_stock.method_used}</div>
                </div>
                <div className="p-2 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-500">Gross Replenishment:</span>
                  <div className="font-mono text-slate-200 font-semibold">{selectedItem.gross_replenishment.toFixed(2)} units</div>
                </div>
                <div className="p-2 bg-slate-950 rounded border border-slate-800">
                  <span className="text-slate-500">Order Quantity (Ceil):</span>
                  <div className="font-mono text-sky-400 font-semibold">{selectedItem.replenishment_qty} units</div>
                </div>
              </div>

              {selectedItem.warnings && selectedItem.warnings.length > 0 && (
                <div className="text-[11px] text-amber-400/90 space-y-0.5">
                  <span className="font-semibold">Algorithm Warnings:</span>
                  {selectedItem.warnings.map((w, i) => (
                    <p key={i}>&bull; {w}</p>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setSelectedItem(null)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-lg"
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
