import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";
import { ForecastingTab } from "../components/ForecastingTab";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";

describe("ForecastingTab Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("handles forecasting generation and displays real forecast metrics and backtesting", async () => {
    vi.spyOn(api, "fetchProducts").mockResolvedValue([
      { id: 1, sku: "PRD-MILK", name: "Whole Milk 1L", category: "Dairy", unit_of_measure: "units", shelf_life_days: 14, unit_cost: 1.5, unit_price: 2.8, holding_cost_per_day: 0.02, lost_sales_penalty: 5.0, storage_temp_c: 4.0, weight_kg: 1.0 },
    ]);
    vi.spyOn(api, "fetchDestinations").mockResolvedValue([
      { id: 1, code: "DST-001", name: "Center City Market", channel_type: "Supermarket", city: "Philadelphia", state: "PA", daily_receiving_capacity_units: 3000, latitude: 39.95, longitude: -75.16 },
    ]);
    vi.spyOn(api, "fetchDemandHistory").mockResolvedValue({
      total: 30,
      limit: 60,
      offset: 0,
      records: [
        { id: 1, destination_id: 1, product_id: 1, demand_date: "2026-10-01", quantity_demanded: 45, quantity_sold: 45, is_simulated: true },
      ],
    });

    const generateSpy = vi.spyOn(api, "generateForecast").mockResolvedValue({
      product_id: 1,
      product_sku: "PRD-MILK",
      destination_id: 1,
      destination_code: "DST-001",
      generated_at: new Date().toISOString(),
      horizon_days: 7,
      method: "ewma",
      method_available: true,
      daily_forecasts: [
        { date: "2026-10-25", value: 50.2 },
        { date: "2026-10-26", value: 52.1 },
      ],
      total_demand: 350.5,
      daily_mean_demand: 50.1,
      forecasted_units: 351,
      history_observations_used: 90,
      warnings: ["Simulated demand stream"],
      is_simulated_data: true,
    });

    renderWithClient(<ForecastingTab />);

    await waitFor(() => {
      expect(screen.getByText(/Whole Milk 1L/)).toBeInTheDocument();
    });

    // Click Generate Forecast
    fireEvent.click(screen.getByTestId("generate-forecast-btn"));

    await waitFor(() => {
      expect(generateSpy).toHaveBeenCalled();
      expect(screen.getByTestId("forecast-summary")).toBeInTheDocument();
    });

    expect(screen.getByText("351 units")).toBeInTheDocument();
    expect(screen.getByText("50.1 u/day")).toBeInTheDocument();
    expect(screen.getByText("90 history days used")).toBeInTheDocument();
  });
});
