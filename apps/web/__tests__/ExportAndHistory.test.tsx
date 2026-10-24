import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";
import { HistoryTab } from "../components/HistoryTab";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";
import { generateShipmentsCSV } from "../lib/export";

describe("Export and History Functions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("generates correctly formatted and escaped CSV with headers and disclaimers", () => {
    const mockPlan: api.PlanResponse = {
      run_code: "PLAN-20261024-CSV",
      dataset_version: "v1.0-seed-42",
      forecast_identifier: "ewma_7d",
      solver_status: "OPTIMAL",
      created_at: "2026-10-24T12:00:00Z",
      optimization_profile: "balanced",
      metrics: {
        total_shipped_units: 500,
        total_transport_cost: 120.5,
        destinations_at_risk: 1,
        stockouts_prevented: 1,
      },
      shipments: [
        {
          id: 1,
          source_warehouse_code: "WH-PHL",
          destination_code: "DST-001",
          destination_name: 'Supermarket "Main", PA', // Contains quotes and comma!
          product_sku: "PRD-MILK",
          product_name: "Whole Milk, 1L", // Contains comma!
          recommended_units: 500,
          unit_transport_cost: 0.241,
          total_transport_cost: 120.5,
          lead_time_days: 1.0,
          reasoning: "Cheapest route, timely delivery.",
        },
      ],
      stockout_risks: [],
      verification: {
        is_feasible: true,
        violations_count: 0,
        violations: [],
        recalculated_cost: 120.5,
        recalculated_units: 500,
        recalculated_fulfilled: 500,
        recalculated_unmet: 0,
      },
    };

    const csv = generateShipmentsCSV(mockPlan);

    // Assert CSV contains disclaimer
    expect(csv).toContain("# StockWise AI - Planned Distribution Recommendations");
    expect(csv).toContain("# DISCLAIMER: Planned shipment recommendation only. Not a confirmed dispatch order.");
    expect(csv).toContain("# Planning Run Code: PLAN-20261024-CSV");

    // Assert CSV column headers
    expect(csv).toContain("Run Code,Source Warehouse,Destination Code,Destination Name,Product SKU,Product Name,Recommended Units,Unit Transport Cost ($),Total Transport Cost ($),Lead Time (Days),Planner Rationale");

    // Assert properly escaped values
    expect(csv).toContain('"Supermarket ""Main"", PA"');
    expect(csv).toContain('"Whole Milk, 1L"');
    expect(csv).toContain('"Cheapest route, timely delivery."');
  });

  it("renders planning runs history and opens detail inspector", async () => {
    vi.spyOn(api, "fetchPlanningRuns").mockResolvedValue({
      total: 1,
      limit: 15,
      offset: 0,
      runs: [
        {
          id: 1,
          run_code: "PLAN-HIST-001",
          dataset_version_id: 1,
          forecast_identifier: "ewma_7d",
          solver_status: "OPTIMAL",
          total_transport_cost: 4120.0,
          total_shipped_units: 18000,
          stockout_risk_count: 2,
          status: "SUCCESS",
          created_at: new Date().toISOString(),
        },
      ],
    });

    vi.spyOn(api, "fetchPlanningRunByCode").mockResolvedValue({
      run_code: "PLAN-HIST-001",
      dataset_version: "v1.0-seed-42",
      forecast_identifier: "ewma_7d",
      solver_status: "OPTIMAL",
      created_at: new Date().toISOString(),
      optimization_profile: "balanced",
      metrics: {
        total_shipped_units: 18000,
        total_transport_cost: 4120.0,
        destinations_at_risk: 2,
        stockouts_prevented: 2,
        fulfillment_rate: 1.0,
      },
      shipments: [
        {
          id: 1,
          source_warehouse_code: "WH-PHL",
          destination_code: "DST-001",
          destination_name: "Center City Market",
          product_sku: "PRD-MILK",
          product_name: "Whole Milk 1L",
          recommended_units: 1000,
          unit_transport_cost: 0.20,
          total_transport_cost: 200.0,
        },
      ],
      stockout_risks: [],
    });

    renderWithClient(<HistoryTab />);

    await waitFor(() => {
      expect(screen.getByText("PLAN-HIST-001")).toBeInTheDocument();
      expect(screen.getByText("$4120.00")).toBeInTheDocument();
    });

    // Click Inspect
    fireEvent.click(screen.getByText("Inspect"));

    await waitFor(() => {
      expect(screen.getByText("Historical Plan Inspection")).toBeInTheDocument();
      expect(screen.getByText("Center City Market (DST-001)")).toBeInTheDocument();
    });
  });
});
