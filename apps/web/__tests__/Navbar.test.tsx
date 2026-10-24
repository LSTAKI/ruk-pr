import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { Navbar } from "../components/Navbar";
import { renderWithClient } from "./test-utils";
import * as api from "../lib/api";

describe("Navbar Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders StockWise AI branding and navigation tabs", () => {
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      status: "healthy",
      environment: "development",
      database_connected: true,
      version: "1.0.0",
      active_dataset_version: "v1.0-seed-42",
    });

    const onSelectTab = vi.fn();
    renderWithClient(
      <Navbar activeTab="overview" onSelectTab={onSelectTab} activeDatasetVersion="v1.0-seed-42" />
    );

    expect(screen.getByText("StockWise AI")).toBeInTheDocument();
    expect(screen.getByText("LOCAL-FIRST")).toBeInTheDocument();
    expect(screen.getByTestId("nav-tab-overview")).toBeInTheDocument();
    expect(screen.getByTestId("nav-tab-inventory")).toBeInTheDocument();
    expect(screen.getByTestId("nav-tab-forecasting")).toBeInTheDocument();
    expect(screen.getByTestId("nav-tab-replenishment")).toBeInTheDocument();
    expect(screen.getByTestId("nav-tab-optimization")).toBeInTheDocument();
    expect(screen.getByTestId("nav-tab-scenarios")).toBeInTheDocument();
    expect(screen.getByTestId("nav-tab-history")).toBeInTheDocument();
  });

  it("calls onSelectTab when a tab is clicked", () => {
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      status: "healthy",
      environment: "development",
      database_connected: true,
      version: "1.0.0",
    });

    const onSelectTab = vi.fn();
    renderWithClient(
      <Navbar activeTab="overview" onSelectTab={onSelectTab} />
    );

    fireEvent.click(screen.getByTestId("nav-tab-inventory"));
    expect(onSelectTab).toHaveBeenCalledWith("inventory");

    fireEvent.click(screen.getByTestId("nav-tab-optimization"));
    expect(onSelectTab).toHaveBeenCalledWith("optimization");
  });

  it("displays Backend Disconnected status if health check fails", async () => {
    vi.spyOn(api, "fetchHealth").mockRejectedValue(new Error("Connection refused"));

    renderWithClient(
      <Navbar activeTab="overview" onSelectTab={vi.fn()} />
    );

    await waitFor(() => {
      expect(screen.getByText("Backend Disconnected")).toBeInTheDocument();
    });
  });
});
