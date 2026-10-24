"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navbar, TabType } from "@/components/Navbar";
import { OverviewTab } from "@/components/OverviewTab";
import { InventoryTab } from "@/components/InventoryTab";
import { ForecastingTab } from "@/components/ForecastingTab";
import { ReplenishmentTab } from "@/components/ReplenishmentTab";
import { OptimizationTab } from "@/components/OptimizationTab";
import { ScenarioTab } from "@/components/ScenarioTab";
import { HistoryTab } from "@/components/HistoryTab";
import { fetchInventoryOverview, PlanResponse } from "@/lib/api";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [currentPlan, setCurrentPlan] = useState<PlanResponse | null>(null);

  const { data: overview } = useQuery({
    queryKey: ["inventory-overview"],
    queryFn: fetchInventoryOverview,
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-sky-500/30 selection:text-sky-200">
      {/* Top Application Shell & Navigation */}
      <Navbar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        activeDatasetVersion={overview?.dataset_version}
      />

      {/* Main Control Tower Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === "overview" && (
          <OverviewTab onNavigateTab={(tab) => setActiveTab(tab)} />
        )}

        {activeTab === "inventory" && <InventoryTab />}

        {activeTab === "forecasting" && <ForecastingTab />}

        {activeTab === "replenishment" && <ReplenishmentTab />}

        {activeTab === "optimization" && (
          <OptimizationTab
            currentPlan={currentPlan}
            onPlanGenerated={(plan) => setCurrentPlan(plan)}
          />
        )}

        {activeTab === "scenarios" && <ScenarioTab />}

        {activeTab === "history" && (
          <HistoryTab
            onLoadRunToDashboard={(plan) => {
              setCurrentPlan(plan);
              setActiveTab("optimization");
            }}
          />
        )}
      </main>

      {/* Control Tower Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-4 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div>
            StockWise AI &bull; FMCG Distribution Intelligence Engine &bull; Local-First Architecture
          </div>
          <div className="font-mono text-[11px] text-slate-600">
            Next.js App Router &bull; FastAPI Backend &bull; Google OR-Tools MIP
          </div>
        </div>
      </footer>
    </div>
  );
}
