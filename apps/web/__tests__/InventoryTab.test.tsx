import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import React from "react";
import { InventoryTab } from "../components/InventoryTab";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";

describe("InventoryTab Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches and renders inventory batches with usable vs on-hand distinction", async () => {
    vi.spyOn(api, "fetchWarehouses").mockResolvedValue([
      { id: 1, code: "WH-PHL", name: "Philadelphia Hub", city: "Philadelphia", state: "PA", capacity_units: 30000, daily_dispatch_capacity_units: 15000, latitude: 39.95, longitude: -75.16 },
    ]);
    vi.spyOn(api, "fetchProducts").mockResolvedValue([
      { id: 1, sku: "PRD-MILK", name: "Whole Milk 1L", category: "Dairy", unit_of_measure: "units", shelf_life_days: 14, unit_cost: 1.5, unit_price: 2.8, holding_cost_per_day: 0.02, lost_sales_penalty: 5.0, storage_temp_c: 4.0, weight_kg: 1.0 },
    ]);
    vi.spyOn(api, "fetchInventoryBatches").mockResolvedValue({
      total: 2,
      limit: 50,
      offset: 0,
      batches: [
        {
          id: 1,
          warehouse_id: 1,
          warehouse_code: "WH-PHL",
          product_id: 1,
          product_sku: "PRD-MILK",
          product_name: "Whole Milk 1L",
          batch_lot: "LOT-2026-001",
          on_hand_units: 1000,
          reserved_units: 200,
          available_units: 800,
          usable_units: 800,
          unit_cost: 1.5,
          expiry_date: new Date(Date.now() + 10 * 86400000).toISOString(),
          batch_status: "AVAILABLE",
        },
        {
          id: 2,
          warehouse_id: 1,
          warehouse_code: "WH-PHL",
          product_id: 1,
          product_sku: "PRD-MILK",
          product_name: "Whole Milk 1L",
          batch_lot: "LOT-2026-002",
          on_hand_units: 500,
          reserved_units: 0,
          available_units: 500,
          usable_units: 0, // Quarantined: 0 usable!
          unit_cost: 1.5,
          expiry_date: new Date(Date.now() + 15 * 86400000).toISOString(),
          batch_status: "QUARANTINED",
        },
      ],
    });

    renderWithClient(<InventoryTab />);

    await waitFor(() => {
      expect(screen.getByText("LOT-2026-001")).toBeInTheDocument();
      expect(screen.getByText("LOT-2026-002")).toBeInTheDocument();
    });

    // Check on-hand vs usable
    expect(screen.getByText("1,000")).toBeInTheDocument(); // on-hand LOT-1
    expect(screen.getAllByText("800").length).toBeGreaterThan(0); // available & usable
    expect(screen.getAllByText("QUARANTINED (Hold)").length).toBeGreaterThan(0); // status badge & select
    expect(screen.getAllByText(/AVAILABLE/).length).toBeGreaterThan(0);
  });
});
