import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";
import { ScenarioTab } from "../components/ScenarioTab";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";

describe("ScenarioTab Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("executes multi-profile scenario comparison and calculates real differences", async () => {
    const makeMockPlan = (profile: string, cost: number, units: number, rate: number): api.PlanResponse => ({
      run_code: `PLAN-${profile.toUpperCase()}`,
      dataset_version: "v1.0-seed-42",
      forecast_identifier: "ewma_7d",
      solver_status: "OPTIMAL",
      created_at: new Date().toISOString(),
      optimization_profile: profile,
      metrics: {
        total_shipped_units: units,
        total_transport_cost: cost,
        destinations_at_risk: 0,
        stockouts_prevented: 4,
        total_demanded_units: 15000,
        total_unmet_units: 15000 - units,
        fulfillment_rate: rate,
        solver_runtime_seconds: 0.5,
        expiry_waste_modeled: false,
      },
      shipments: [],
      stockout_risks: [],
      verification: {
        is_feasible: true,
        violations_count: 0,
        violations: [],
        recalculated_cost: cost,
        recalculated_units: units,
        recalculated_fulfilled: units,
        recalculated_unmet: 15000 - units,
      },
    });

    const runSpy = vi.spyOn(api, "executePlanRun").mockImplementation(async (payload) => {
      const p = payload?.optimization_profile;
      if (p === "cost_first") return makeMockPlan("cost_first", 2400.0, 12000, 0.80);
      if (p === "service_first") return makeMockPlan("service_first", 3100.0, 15000, 1.00);
      return makeMockPlan("balanced", 2800.0, 14500, 0.967);
    });

    renderWithClient(<ScenarioTab />);

    // Click Run Scenario Comparison
    fireEvent.click(screen.getByTestId("run-scenario-comparison-btn"));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalledTimes(3);
      expect(screen.getByTestId("scenario-results")).toBeInTheDocument();
    });

    // Check displayed metrics
    expect(screen.getByText("$2400.00")).toBeInTheDocument();
    expect(screen.getByText("$3100.00")).toBeInTheDocument();
    expect(screen.getByText("$2800.00")).toBeInTheDocument();

    // Check that unmodeled expiry is explicitly rendered as "Not Modeled"
    const notModeledCells = screen.getAllByText("Not Modeled");
    expect(notModeledCells.length).toBeGreaterThan(0);

    // Check service premium delta calculation: 15000 - 12000 = 3000 units, 3100 - 2400 = $700.00
    expect(screen.getByText(/3,000 additional units/i)).toBeInTheDocument();
    expect(screen.getByText(/\+\$700\.00/i)).toBeInTheDocument();
  });
});
