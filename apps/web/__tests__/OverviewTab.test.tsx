import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import React from "react";
import { OverviewTab } from "../components/OverviewTab";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";

describe("OverviewTab Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders loading skeleton initially", () => {
    vi.spyOn(api, "fetchInventoryOverview").mockImplementation(() => new Promise(() => {}));
    vi.spyOn(api, "fetchReplenishmentSummary").mockImplementation(() => new Promise(() => {}));
    vi.spyOn(api, "fetchPlanningRuns").mockImplementation(() => new Promise(() => {}));

    renderWithClient(<OverviewTab onNavigateTab={vi.fn()} />);
    expect(screen.getByTestId("overview-loading")).toBeInTheDocument();
  });

  it("renders real API metrics correctly upon load", async () => {
    vi.spyOn(api, "fetchInventoryOverview").mockResolvedValue({
      total_warehouses: 4,
      total_destinations: 50,
      total_products: 16,
      total_units_on_hand: 52000,
      total_units_reserved: 4000,
      total_units_available: 48000,
      total_units_usable: 46000,
      dataset_version: "v1.0-seed-42",
      warehouses: [
        {
          id: 1,
          code: "WH-PHL",
          name: "Philadelphia Hub",
          city: "Philadelphia",
          state: "PA",
          capacity_units: 30000,
          daily_dispatch_capacity_units: 15000,
          latitude: 39.95,
          longitude: -75.16,
        },
      ],
      products: [],
    });

    vi.spyOn(api, "fetchReplenishmentSummary").mockResolvedValue({
      generated_at: new Date().toISOString(),
      total: 800,
      limit: 1,
      offset: 0,
      warehouses_evaluated: ["WH-PHL"],
      as_of_date: "2026-10-24",
      requirements: [],
      total_replenishment_units: 18200,
      critical_count: 5,
      high_count: 12,
      moderate_count: 20,
      low_count: 763,
      insufficient_data_count: 0,
      caveats: [],
    });

    vi.spyOn(api, "fetchPlanningRuns").mockResolvedValue({
      total: 1,
      limit: 5,
      offset: 0,
      runs: [
        {
          id: 1,
          run_code: "PLAN-20261024-TEST",
          dataset_version_id: 1,
          forecast_identifier: "ewma_7d",
          solver_status: "OPTIMAL",
          total_transport_cost: 3450.25,
          total_shipped_units: 14200,
          stockout_risk_count: 2,
          status: "SUCCESS",
          created_at: new Date().toISOString(),
        },
      ],
    });

    renderWithClient(<OverviewTab onNavigateTab={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("overview-content")).toBeInTheDocument();
    });

    // Check inventory accounting metrics
    expect(screen.getByText("52,000")).toBeInTheDocument(); // on-hand
    expect(screen.getByText("4,000")).toBeInTheDocument(); // reserved
    expect(screen.getByText("48,000")).toBeInTheDocument(); // available
    expect(screen.getByText("46,000")).toBeInTheDocument(); // usable

    // Check replenishment counts
    expect(screen.getByText("5 Critical")).toBeInTheDocument();
    expect(screen.getByText("18,200")).toBeInTheDocument();

    // Check latest run
    expect(screen.getByText("PLAN-20261024-TEST")).toBeInTheDocument();
    expect(screen.getByText("$3450.25")).toBeInTheDocument();
  });

  it("renders error state when backend is unreachable", async () => {
    vi.spyOn(api, "fetchInventoryOverview").mockRejectedValue(new Error("Network Error"));
    vi.spyOn(api, "fetchReplenishmentSummary").mockResolvedValue({} as any);
    vi.spyOn(api, "fetchPlanningRuns").mockResolvedValue({} as any);

    renderWithClient(<OverviewTab onNavigateTab={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId("overview-error")).toBeInTheDocument();
      expect(screen.getByText(/Failed to connect to StockWise backend/i)).toBeInTheDocument();
    });
  });
});
