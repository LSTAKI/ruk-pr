import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { KPISummary } from "../components/KPISummary";
import { PlanMetrics } from "../lib/api";

describe("KPISummary Component", () => {
  it("renders empty placeholders when no metrics are provided", () => {
    render(<KPISummary />);
    expect(screen.getByTestId("kpi-shipments")).toHaveTextContent("—");
    expect(screen.getByTestId("kpi-cost")).toHaveTextContent("—");
    expect(screen.getByTestId("kpi-expiry")).toHaveTextContent("—");
    expect(screen.getByTestId("kpi-stockout")).toHaveTextContent("—");
  });

  it("renders accurate formatted metrics when provided", () => {
    const mockMetrics: PlanMetrics = {
      total_shipped_units: 14500,
      total_transport_cost: 3240.5,
      avg_expiry_risk_pct: 2.1,
      stockouts_prevented: 8,
      destinations_at_risk: 4,
    };

    render(<KPISummary metrics={mockMetrics} />);
    expect(screen.getByTestId("kpi-shipments")).toHaveTextContent("14,500 units");
    expect(screen.getByTestId("kpi-cost")).toHaveTextContent("$3,240.50");
    expect(screen.getByTestId("kpi-expiry")).toHaveTextContent("2.1%");
    expect(screen.getByTestId("kpi-stockout")).toHaveTextContent("4 stores");
  });
});
