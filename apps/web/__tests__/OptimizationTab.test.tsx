import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";
import { OptimizationTab } from "../components/OptimizationTab";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";

describe("OptimizationTab Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("submits optimization request and calls onPlanGenerated", async () => {
    const mockPlan: api.PlanResponse = {
      run_code: "PLAN-20261024-SUCC",
      dataset_version: "v1.0-seed-42",
      forecast_identifier: "ewma_7d",
      solver_status: "OPTIMAL",
      created_at: new Date().toISOString(),
      optimization_profile: "balanced",
      metrics: {
        total_shipped_units: 12500,
        total_transport_cost: 2840.5,
        destinations_at_risk: 3,
        stockouts_prevented: 3,
        total_demanded_units: 12500,
        total_unmet_units: 0,
        fulfillment_rate: 1.0,
        solver_runtime_seconds: 0.85,
        expiry_waste_modeled: false,
      },
      shipments: [
        {
          id: 1,
          source_warehouse_code: "WH-PHL",
          destination_code: "DST-001",
          destination_name: "Center City Market",
          product_sku: "PRD-MILK",
          product_name: "Whole Milk 1L",
          recommended_units: 400,
          unit_transport_cost: 0.15,
          total_transport_cost: 60.0,
          lead_time_days: 1.0,
          reasoning: "Least transport cost route from Philadelphia Hub",
        },
      ],
      stockout_risks: [],
      unmet_demands: [],
      verification: {
        is_feasible: true,
        violations_count: 0,
        violations: [],
        recalculated_cost: 2840.5,
        recalculated_units: 12500,
        recalculated_fulfilled: 12500,
        recalculated_unmet: 0,
      },
    };

    const runSpy = vi.spyOn(api, "executePlanRun").mockResolvedValue(mockPlan);
    const onPlanGenerated = vi.fn();

    renderWithClient(
      <OptimizationTab currentPlan={null} onPlanGenerated={onPlanGenerated} />
    );

    // Click Run Local Optimizer
    fireEvent.click(screen.getByTestId("run-optimization-submit-btn"));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalled();
      expect(onPlanGenerated).toHaveBeenCalledWith(mockPlan);
    });
  });

  it("renders plan outcome card, verifier status, and shipments table when plan is loaded", () => {
    const mockPlan: api.PlanResponse = {
      run_code: "PLAN-20261024-SUCC",
      dataset_version: "v1.0-seed-42",
      forecast_identifier: "ewma_7d",
      solver_status: "OPTIMAL",
      created_at: new Date().toISOString(),
      optimization_profile: "balanced",
      metrics: {
        total_shipped_units: 12500,
        total_transport_cost: 2840.5,
        destinations_at_risk: 3,
        stockouts_prevented: 3,
        total_demanded_units: 12500,
        total_unmet_units: 0,
        fulfillment_rate: 1.0,
        solver_runtime_seconds: 0.85,
        expiry_waste_modeled: false,
      },
      shipments: [
        {
          id: 1,
          source_warehouse_code: "WH-PHL",
          destination_code: "DST-001",
          destination_name: "Center City Market",
          product_sku: "PRD-MILK",
          product_name: "Whole Milk 1L",
          recommended_units: 400,
          unit_transport_cost: 0.15,
          total_transport_cost: 60.0,
          lead_time_days: 1.0,
          reasoning: "Least transport cost route from Philadelphia Hub",
        },
      ],
      stockout_risks: [],
      unmet_demands: [],
      verification: {
        is_feasible: true,
        violations_count: 0,
        violations: [],
        recalculated_cost: 2840.5,
        recalculated_units: 12500,
        recalculated_fulfilled: 12500,
        recalculated_unmet: 0,
      },
    };

    renderWithClient(
      <OptimizationTab currentPlan={mockPlan} onPlanGenerated={vi.fn()} />
    );

    expect(screen.getByTestId("solver-outcome-card")).toBeInTheDocument();
    expect(screen.getByText("OPTIMAL")).toBeInTheDocument();
    expect(screen.getByText("Verifier: Feasible")).toBeInTheDocument();
    expect(screen.getByText("12,500 u")).toBeInTheDocument();
    expect(screen.getByText("$2840.50")).toBeInTheDocument();

    // Check shipment table
    expect(screen.getByText("Center City Market")).toBeInTheDocument();
    expect(screen.getByText("WH-PHL")).toBeInTheDocument();
    expect(screen.getByText("$60.00")).toBeInTheDocument();
  });

  it("prevents displaying failed or infeasible solver runs as successful", () => {
    const failedPlan: api.PlanResponse = {
      run_code: "PLAN-20261024-FAIL",
      dataset_version: "v1.0-seed-42",
      forecast_identifier: "ewma_7d",
      solver_status: "TARGET_UNACHIEVABLE",
      status_message: "Network capacity insufficient to achieve 95% fulfillment floor.",
      created_at: new Date().toISOString(),
      optimization_profile: "cost_first",
      metrics: {
        total_shipped_units: 0,
        total_transport_cost: 0,
        destinations_at_risk: 10,
        stockouts_prevented: 0,
        fulfillment_rate: 0.0,
      },
      shipments: [],
      stockout_risks: [],
    };

    renderWithClient(
      <OptimizationTab currentPlan={failedPlan} onPlanGenerated={vi.fn()} />
    );

    expect(screen.getByTestId("solver-outcome-card")).toBeInTheDocument();
    expect(screen.getByText("TARGET_UNACHIEVABLE")).toBeInTheDocument();
    expect(
      screen.getByText(/Network capacity insufficient to achieve 95% fulfillment floor/i)
    ).toBeInTheDocument();
    // Must NOT state optimal or feasible!
    expect(screen.queryByText("Verifier: Feasible")).not.toBeInTheDocument();
  });
});
