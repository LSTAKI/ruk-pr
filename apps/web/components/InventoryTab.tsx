"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchInventoryBatches,
  fetchWarehouses,
  fetchProducts,
  InventoryItem,
} from "@/lib/api";
import {
  Package,
  Search,
  AlertTriangle,
  CheckCircle,
  Clock,
  Filter,
  ChevronLeft,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";

export function InventoryTab() {
  const [warehouseId, setWarehouseId] = useState<number | undefined>(undefined);
  const [productId, setProductId] = useState<number | undefined>(undefined);
  const [batchStatus, setBatchStatus] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [page, setPage] = useState<number>(0);
  const pageSize = 50;

  const { data: warehouses } = useQuery({
    queryKey: ["inventory-warehouses"],
    queryFn: fetchWarehouses,
  });

  const { data: products } = useQuery({
    queryKey: ["inventory-products"],
    queryFn: fetchProducts,
  });

  const {
    data: batchData,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["inventory-batches", warehouseId, productId, batchStatus, page],
    queryFn: () =>
      fetchInventoryBatches({
        warehouse_id: warehouseId,
        product_id: productId,
        batch_status: batchStatus || undefined,
        limit: pageSize,
        offset: page * pageSize,
      }),
  });

  const batches = batchData?.batches || [];
  const total = batchData?.total || 0;
  const totalPages = Math.ceil(total / pageSize);

  const filtered = batches.filter((b) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      b.batch_lot.toLowerCase().includes(term) ||
      (b.product_sku && b.product_sku.toLowerCase().includes(term)) ||
      (b.product_name && b.product_name.toLowerCase().includes(term)) ||
      (b.warehouse_code && b.warehouse_code.toLowerCase().includes(term))
    );
  });

  const getStatusBadge = (status: string, usable: number = 0, expiryDateStr: string) => {
    const isExpired = new Date(expiryDateStr) <= new Date();
    if (isExpired || status === "EXPIRED") {
      return (
        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-rose-950/80 text-rose-400 border border-rose-800/80">
          <ShieldAlert className="h-3 w-3" />
          <span>EXPIRED (0 Usable)</span>
        </span>
      );
    }
    if (status === "QUARANTINED") {
      return (
        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-orange-950/80 text-orange-400 border border-orange-800/80">
          <AlertTriangle className="h-3 w-3" />
          <span>QUARANTINED (Hold)</span>
        </span>
      );
    }
    if (status === "RESERVED") {
      return (
        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-amber-950/80 text-amber-400 border border-amber-800/80">
          <Clock className="h-3 w-3" />
          <span>RESERVED</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-950/80 text-emerald-400 border border-emerald-800/80">
        <CheckCircle className="h-3 w-3" />
        <span>AVAILABLE</span>
      </span>
    );
  };

  const getExpiryLabel = (dateStr: string) => {
    const expiry = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.ceil((expiry.getTime() - now.getTime()) / (1000 * 3600 * 24));

    if (diffDays <= 0) {
      return <span className="text-rose-400 font-semibold">Expired</span>;
    }
    if (diffDays <= 30) {
      return <span className="text-amber-400 font-semibold">{diffDays}d (Near Expiry)</span>;
    }
    return <span className="text-slate-300">{diffDays}d remaining</span>;
  };

  return (
    <div className="space-y-6" data-testid="inventory-explorer">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white">Multi-Echelon Inventory Explorer</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Batch-level accounting of physical on-hand, reservations, usable supply, and FEFO expiry tracking
        </p>
      </div>

      {/* Accounting Notice */}
      <div className="rounded-lg border border-sky-900/60 bg-sky-950/30 p-3.5 text-xs text-slate-300 flex items-start space-x-3">
        <Package className="h-4 w-4 text-sky-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-white">Inventory Accounting Policy:</span>
          <span className="ml-1 text-slate-300">
            Physical on-hand counts reflect total storage units. Only <strong className="text-emerald-400">Usable Inventory</strong> (non-expired, non-quarantined, available stock) is allocatable by the OR-Tools distribution solver.
          </span>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* Warehouse Filter */}
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Regional Hub</label>
            <select
              value={warehouseId ?? ""}
              onChange={(e) => {
                setWarehouseId(e.target.value ? Number(e.target.value) : undefined);
                setPage(0);
              }}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">All Warehouses</option>
              {warehouses?.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.code} - {w.name} ({w.city})
                </option>
              ))}
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
              <option value="">All Products (16 SKUs)</option>
              {products?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} - {p.name}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Batch Accounting Status</label>
            <select
              value={batchStatus}
              onChange={(e) => {
                setBatchStatus(e.target.value);
                setPage(0);
              }}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">All Statuses</option>
              <option value="AVAILABLE">AVAILABLE (Allocatable)</option>
              <option value="RESERVED">RESERVED</option>
              <option value="QUARANTINED">QUARANTINED (Hold)</option>
              <option value="EXPIRED">EXPIRED</option>
              <option value="DEPLETED">DEPLETED</option>
            </select>
          </div>

          {/* Search Term */}
          <div>
            <label className="block text-[11px] font-medium text-slate-400 mb-1">Search Lot / SKU</label>
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search lot, SKU, hub..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg pl-8 pr-2.5 py-1.5 text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>
          </div>
        </div>

        {/* Clear Filters */}
        {(warehouseId !== undefined || productId !== undefined || batchStatus !== "" || searchTerm !== "") && (
          <div className="flex justify-end pt-1">
            <button
              onClick={() => {
                setWarehouseId(undefined);
                setProductId(undefined);
                setBatchStatus("");
                setSearchTerm("");
                setPage(0);
              }}
              className="text-[11px] text-sky-400 hover:text-sky-300"
            >
              Reset All Filters
            </button>
          </div>
        )}
      </div>

      {/* Batches Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-medium">
                <th className="py-3 px-3">Batch Lot</th>
                <th className="py-3 px-3">Hub</th>
                <th className="py-3 px-3">Product / SKU</th>
                <th className="py-3 px-3 text-right">On-Hand</th>
                <th className="py-3 px-3 text-right">Reserved</th>
                <th className="py-3 px-3 text-right">Available</th>
                <th className="py-3 px-3 text-right">Usable</th>
                <th className="py-3 px-3 text-right">Unit Cost</th>
                <th className="py-3 px-3">Expiry Date</th>
                <th className="py-3 px-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {isLoading ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-400 animate-pulse">
                    Loading inventory batches from database...
                  </td>
                </tr>
              ) : isError ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-rose-400">
                    Failed to load batches: {error instanceof Error ? error.message : "Error"}
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500">
                    No inventory batches match current filters.
                  </td>
                </tr>
              ) : (
                filtered.map((batch: InventoryItem) => (
                  <tr key={batch.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3 font-mono font-medium text-white">{batch.batch_lot}</td>
                    <td className="py-2.5 px-3 font-mono text-sky-400">{batch.warehouse_code || `WH-${batch.warehouse_id}`}</td>
                    <td className="py-2.5 px-3">
                      <div className="font-medium text-slate-200">{batch.product_name || `Product ${batch.product_id}`}</div>
                      <div className="text-[10px] font-mono text-slate-500">{batch.product_sku}</div>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {batch.on_hand_units.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-amber-400">
                      {batch.reserved_units.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-sky-400">
                      {(batch.available_units ?? Math.max(0, batch.on_hand_units - batch.reserved_units)).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-semibold text-emerald-400">
                      {(batch.usable_units ?? 0).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      ${batch.unit_cost.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-[11px]">
                      <div>{new Date(batch.expiry_date).toLocaleDateString()}</div>
                      <div className="text-[10px]">{getExpiryLabel(batch.expiry_date)}</div>
                    </td>
                    <td className="py-2.5 px-3">
                      {getStatusBadge(batch.batch_status, batch.usable_units ?? 0, batch.expiry_date)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800 text-xs text-slate-400">
          <div>
            Showing {filtered.length} of {total} batches (Page {page + 1} of {Math.max(1, totalPages)})
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
    </div>
  );
}
