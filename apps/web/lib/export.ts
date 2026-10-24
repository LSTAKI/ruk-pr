/**
 * StockWise AI - CSV Export Utilities
 * Generates safely escaped, audit-ready CSV exports for planning runs.
 */

import { PlanResponse, Shipment } from "./api";

function escapeCSV(val: unknown): string {
  if (val === null || val === undefined) return "";
  const str = String(val);
  if (str.includes(",") || str.includes('"') || str.includes("\n") || str.includes("\r")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function generateShipmentsCSV(plan: PlanResponse): string {
  const lines: string[] = [];

  // Metadata comments / disclaimers
  lines.push("# StockWise AI - Planned Distribution Recommendations");
  lines.push(`# Planning Run Code: ${plan.run_code}`);
  lines.push(`# Optimization Profile: ${plan.optimization_profile || "balanced"}`);
  lines.push(`# Solver Status: ${plan.solver_status}`);
  lines.push(`# Generated At: ${plan.created_at}`);
  lines.push(`# Total Shipped Units: ${plan.metrics.total_shipped_units}`);
  lines.push(`# Total Freight Cost: $${plan.metrics.total_transport_cost.toFixed(2)}`);
  lines.push(`# Verification Status: ${plan.verification?.is_feasible ? "FEASIBLE" : "UNVERIFIED/VIOLATED"}`);
  lines.push("# DISCLAIMER: Planned shipment recommendation only. Not a confirmed dispatch order.");
  lines.push("");

  // Column headers
  const headers = [
    "Run Code",
    "Source Warehouse",
    "Destination Code",
    "Destination Name",
    "Product SKU",
    "Product Name",
    "Recommended Units",
    "Unit Transport Cost ($)",
    "Total Transport Cost ($)",
    "Lead Time (Days)",
    "Planner Rationale",
  ];
  lines.push(headers.map(escapeCSV).join(","));

  // Rows
  for (const s of plan.shipments) {
    const row = [
      plan.run_code,
      s.source_warehouse_code,
      s.destination_code,
      s.destination_name,
      s.product_sku,
      s.product_name,
      s.recommended_units,
      s.unit_transport_cost.toFixed(2),
      s.total_transport_cost.toFixed(2),
      s.lead_time_days !== undefined ? s.lead_time_days : 1.0,
      s.reasoning || "Optimized allocation based on minimum freight cost and available batch stock",
    ];
    lines.push(row.map(escapeCSV).join(","));
  }

  return lines.join("\r\n");
}

export function downloadCSV(filename: string, csvContent: string): void {
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  link.style.visibility = "hidden";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
