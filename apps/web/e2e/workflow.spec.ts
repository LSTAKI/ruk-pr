import { test, expect } from "@playwright/test";

test.describe("StockWise AI End-to-End Workflow", () => {
  test("loads the dashboard and displays core sections", async ({ page }) => {
    await page.goto("/");

    // Verify main header
    await expect(
      page.getByRole("heading", { name: "Distribution Intelligence & Inventory Engine" })
    ).toBeVisible();

    // Verify presence of optimizer run button
    const runBtn = page.getByTestId("run-optimizer-btn");
    await expect(runBtn).toBeVisible();

    // Verify KPI sections
    await expect(page.getByTestId("kpi-shipments")).toBeVisible();
    await expect(page.getByTestId("kpi-cost")).toBeVisible();
  });
});
