import React, { useState } from "react";
import { Shipment } from "@/lib/api";
import { Info, Search } from "lucide-react";

interface ShipmentTableProps {
  shipments: Shipment[];
}

export function ShipmentTable({ shipments }: ShipmentTableProps) {
  const [searchTerm, setSearchTerm] = useState("");

  const filtered = shipments.filter(
    (s) =>
      s.product_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.destination_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.source_warehouse_code.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="rounded-xl border border-border bg-card/60 backdrop-blur-sm p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-white">Recommended FMCG Shipments</h3>
          <p className="text-xs text-muted-foreground">
            Linear solver multi-echelon allocation decisions with explainable reasoning
          </p>
        </div>

        <div className="relative">
          <Search className="h-3.5 w-3.5 absolute left-3 top-2.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Filter product, hub, or store..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="text-xs bg-secondary/60 border border-border rounded-lg pl-8 pr-3 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary w-full sm:w-64"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border/80 text-muted-foreground">
              <th className="py-2.5 px-3 font-medium">SKU / Product</th>
              <th className="py-2.5 px-3 font-medium">Source Hub</th>
              <th className="py-2.5 px-3 font-medium">Destination</th>
              <th className="py-2.5 px-3 font-medium text-right">Units</th>
              <th className="py-2.5 px-3 font-medium text-right">Freight Cost</th>
              <th className="py-2.5 px-3 font-medium">Planner Rationale</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-6 text-center text-muted-foreground">
                  No shipments matching search criteria.
                </td>
              </tr>
            ) : (
              filtered.slice(0, 15).map((s, idx) => (
                <tr key={`${s.id}-${idx}`} className="hover:bg-secondary/30 transition-colors">
                  <td className="py-2.5 px-3">
                    <div className="font-medium text-white">{s.product_name}</div>
                    <div className="text-[10px] text-muted-foreground font-mono">{s.product_sku}</div>
                  </td>
                  <td className="py-2.5 px-3 font-mono font-medium text-sky-400">
                    {s.source_warehouse_code}
                  </td>
                  <td className="py-2.5 px-3">
                    <div className="text-foreground">{s.destination_name}</div>
                    <div className="text-[10px] text-muted-foreground font-mono">{s.destination_code}</div>
                  </td>
                  <td className="py-2.5 px-3 text-right font-mono font-semibold text-white">
                    {s.recommended_units.toLocaleString()}
                  </td>
                  <td className="py-2.5 px-3 text-right font-mono text-emerald-400">
                    ${s.total_transport_cost.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3 max-w-xs text-muted-foreground text-[11px] leading-relaxed">
                    <div className="flex items-start space-x-1.5">
                      <Info className="h-3 w-3 text-primary shrink-0 mt-0.5" />
                      <span>{s.reasoning || "Lowest freight cost routing with available stock."}</span>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {filtered.length > 15 && (
        <p className="text-[11px] text-muted-foreground mt-3 text-right">
          Showing 15 of {filtered.length} generated shipment recommendations.
        </p>
      )}
    </div>
  );
}
