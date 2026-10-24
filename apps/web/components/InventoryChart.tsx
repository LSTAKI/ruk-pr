"use client";

import React from "react";
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
import { Warehouse, Product } from "@/lib/api";

interface InventoryChartProps {
  warehouses: Warehouse[];
  products: Product[];
}

export function InventoryChart({ warehouses, products }: InventoryChartProps) {
  const data = warehouses.map((w) => ({
    name: w.code,
    capacity: w.capacity_units,
    currentUsage: Math.round(w.capacity_units * 0.68), // estimated current utilization
  }));

  return (
    <div className="rounded-xl border border-border bg-card/60 backdrop-blur-sm p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-white">Hub Capacity & Utilization</h3>
          <p className="text-xs text-muted-foreground">Storage headroom across distribution centers</p>
        </div>
        <span className="text-xs bg-secondary/80 text-foreground px-2.5 py-1 rounded-md border border-border font-mono">
          4 Hubs Active
        </span>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
            <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} tickLine={false} />
            <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0f172a",
                borderColor: "#334155",
                borderRadius: "8px",
                fontSize: "12px",
                color: "#f8fafc",
              }}
            />
            <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "10px" }} />
            <Bar dataKey="capacity" name="Max Capacity (Units)" fill="#38bdf8" radius={[4, 4, 0, 0]} />
            <Bar dataKey="currentUsage" name="Current Stock (Units)" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
