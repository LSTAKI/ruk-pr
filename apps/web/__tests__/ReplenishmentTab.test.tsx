import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import React from "react";
import { ReplenishmentTab } from "../components/ReplenishmentTab";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";

describe("ReplenishmentTab Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders prominent GAP-1 and GAP-2 data disclosures", () => {
    vi.spyOn(api, "fetchProducts").mockResolvedValue([]);
    vi.spyOn(api, "fetchDestinations").mockResolvedValue([]);
    vi.spyOn(api, "fetchReplenishmentSummary").mockResolvedValue({
      generated_at: new Date().toISOString(),
      total: 0,
      limit: 50,
      offset: 0,
      warehouses_evaluated: [],
      as_of_date: "2026-10-24",
      requirements: [],
      total_replenishment_units: 0,
      critical_count: 0,
      high_count: 0,
      moderate_count: 0,
      low_count: 0,
      insufficient_data_count: 0,
      caveats: [],
    });

    renderWithClient(<ReplenishmentTab />);

    expect(screen.getByText(/Known Data Gaps \(GAP-1 & GAP-2\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Destination Store On-Hand Inventory \(GAP-1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Committed In-Transit Dispatches \(GAP-2\)/i)).toBeInTheDocument();
  });

  it("renders replenishment requirements and risk badges correctly", async () => {
    vi.spyOn(api, "fetchProducts").mockResolvedValue([]);
    vi.spyOn(api, "fetchDestinations").mockResolvedValue([]);
    vi.spyOn(api, "fetchReplenishmentSummary").mockResolvedValue({
      generated_at: new Date().toISOString(),
      total: 1,
      limit: 50,
      offset: 0,
      warehouses_evaluated: ["WH-PHL"],
      as_of_date: "2026-10-24",
      requirements: [
        {
          product_id: 1,
          product_sku: "PRD-MILK",
          product_name: "Whole Milk 1L",
          destination_id: 1,
          destination_code: "DST-001",
          destination_name: "Center City Market",
          lead_time_days: 1.5,
          warehouse_code: "WH-PHL",
          route_selection_reason: "Fastest route",
          daily_mean_demand: 40.0,
          lead_time_demand: 60.0,
          forecast_method: "ewma",
          forecast_warnings: [],
          safety_stock: {
            safety_stock_units: 24.5,
            safety_stock_int: 25,
            method_used: "formula",
            mean_daily_demand: 40.0,
            lead_time_days: 1.5,
            observations_used: 90,
            warnings: [],
            is_simulated_data: true,
          },
          replenishment_threshold: 84.5,
          destination_usable_units: 0,
          incoming_committed_units: 0,
          projected_position: 0,
          gross_replenishment: 84.5,
          replenishment_qty: 85,
          risk_category: "Critical",
          reason_codes: ["RC_STOCKOUT_RISK"],
          explanation: "Projected position is below replenishment threshold within lead time.",
          warnings: [],
          history_observations_used: 90,
        },
      ],
      total_replenishment_units: 85,
      critical_count: 1,
      high_count: 0,
      moderate_count: 0,
      low_count: 0,
      insufficient_data_count: 0,
      caveats: [],
    });

    renderWithClient(<ReplenishmentTab />);

    await waitFor(() => {
      expect(screen.getByText("Whole Milk 1L")).toBeInTheDocument();
      expect(screen.getByText("Center City Market")).toBeInTheDocument();
      expect(screen.getAllByText(/85\s*u/).length).toBeGreaterThan(0);
      expect(screen.getByText("Critical")).toBeInTheDocument();
    });
  });
});
