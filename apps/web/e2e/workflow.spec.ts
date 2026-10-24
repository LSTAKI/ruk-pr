import { test, expect } from "@playwright/test";

test.describe("StockWise AI End-to-End Workflow & Module Navigation", () => {
  test("loads the application shell, validates local branding, and navigates all 7 operational modules", async ({ page }) => {
    // Navigate to root
    await page.goto("/");

    // 1. Verify Top-Level Branding & Status Indicators
    await expect(page.getByText("StockWise AI", { exact: true })).toBeVisible();
    await expect(page.getByText("LOCAL-FIRST", { exact: true })).toBeVisible();

    // 2. Verify Overview Dashboard
    await expect(page.getByRole("heading", { name: "Distribution Intelligence Overview" })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Network Infrastructure")).toBeVisible();
    await expect(page.getByText("Regional Warehouses")).toBeVisible();
    await expect(page.getByText("Retail Destinations")).toBeVisible();
    await expect(page.getByText("Catalog SKUs")).toBeVisible();

    // 3. Navigate to Inventory Explorer
    await page.getByTestId("nav-tab-inventory").click();
    await expect(page.getByRole("heading", { name: "Multi-Echelon Inventory Explorer" })).toBeVisible();
    await expect(page.getByText("Inventory Accounting Policy:")).toBeVisible();

    // 4. Navigate to Demand Forecasting
    await page.getByTestId("nav-tab-forecasting").click();
    await expect(page.getByRole("heading", { name: "Demand Forecasting & Backtesting Engine" })).toBeVisible();
    await expect(page.getByText("Simulated Demand Disclosure:")).toBeVisible();
    await expect(page.getByTestId("generate-forecast-btn")).toBeVisible();

    // 5. Navigate to Replenishment Planner
    await page.getByTestId("nav-tab-replenishment").click();
    await expect(page.getByRole("heading", { name: "Inventory Position & Replenishment Engine" })).toBeVisible();
    await expect(page.getByText("Operational Model Notice: Known Data Gaps (GAP-1 & GAP-2)")).toBeVisible();

    // 6. Navigate to Optimizer Planner
    await page.getByTestId("nav-tab-optimization").click();
    await expect(page.getByRole("heading", { name: "OR-Tools Distribution Optimizer" })).toBeVisible();
    await expect(page.getByText("Solver Formulation & Profile Controls")).toBeVisible();
    await expect(page.getByTestId("run-optimization-submit-btn")).toBeVisible();

    // 7. Navigate to Scenario Compare
    await page.getByTestId("nav-tab-scenarios").click();
    await expect(page.getByRole("heading", { name: "Multi-Profile Scenario Comparison" })).toBeVisible();
    await expect(page.getByTestId("run-scenario-comparison-btn")).toBeVisible();

    // 8. Navigate to Planning History
    await page.getByTestId("nav-tab-history").click();
    await expect(page.getByRole("heading", { name: "Planning Runs History & Audit Log" })).toBeVisible();
  });

  test("executes real end-to-end optimization run, renders solver outcome, and exports CSV", async ({ page }) => {
    await page.goto("/");

    // 1. Navigate to Optimizer Planner
    await page.getByTestId("nav-tab-optimization").click();
    await expect(page.getByRole("heading", { name: "OR-Tools Distribution Optimizer" })).toBeVisible();

    // 2. Click Run Local Optimizer
    const runBtn = page.getByTestId("run-optimization-submit-btn");
    await expect(runBtn).toBeVisible();
    await runBtn.click();

    // 3. Await Solver Outcome Card with extended timeout for MIP solve
    const outcomeCard = page.getByTestId("solver-outcome-card");
    await expect(outcomeCard).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("OPTIMAL")).toBeVisible();
    await expect(page.getByText("Verifier: Feasible")).toBeVisible();

    // 4. Verify Shipment Recommendations Table Rendering
    await expect(page.getByText("Recommended Allocation Schedule")).toBeVisible();

    // 5. Verify CSV Download Trigger
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^stockwise_shipments_(PLAN|RUN)-.*\.csv$/);
  });
});
