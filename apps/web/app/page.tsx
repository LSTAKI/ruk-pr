"use client";

import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Navbar } from "@/components/Navbar";
import { KPISummary } from "@/components/KPISummary";
import { InventoryChart } from "@/components/InventoryChart";
import { StockoutAlerts } from "@/components/StockoutAlerts";
import { ShipmentTable } from "@/components/ShipmentTable";
import { OptimizationControls } from "@/components/OptimizationControls";
import { fetchInventoryOverview, executePlanRun, PlanResponse } from "@/lib/api";

export default function DashboardPage() {
  const [horizonDays, setHorizonDays] = useState(7);
  const [planResult, setPlanResult] = useState<PlanResponse | null>(null);

  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
  } = useQuery({
    queryKey: ["inventory-overview"],
    queryFn: fetchInventoryOverview,
  });

  const planMutation = useMutation({
    mutationFn: (days: number) =>
      executePlanRun({
        forecast_horizon_days: days,
        parameters: {
          transport_weight: 1.0,
          stockout_penalty_weight: 5.0,
          expiry_risk_weight: 2.5,
          max_solver_time_seconds: 10,
        },
      }),
    onSuccess: (data) => {
      setPlanResult(data);
    },
  });

  const handleRunPlan = () => {
    planMutation.mutate(horizonDays);
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <Navbar activeDatasetVersion={overview?.dataset_version} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Distribution Intelligence & Inventory Engine
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Deterministic multi-echelon network planning and shelf-life constrained optimization
            </p>
          </div>
          <div className="flex items-center space-x-2 text-xs text-muted-foreground">
            <span>Network:</span>
            <span className="font-mono text-white font-medium">
              {overview?.total_warehouses ?? 4} Hubs / {overview?.total_destinations ?? 16} Stores
            </span>
          </div>
        </div>

        {/* Controls */}
        <OptimizationControls
          onRunPlan={handleRunPlan}
          loading={planMutation.isPending}
          horizonDays={horizonDays}
          setHorizonDays={setHorizonDays}
          solverStatus={planResult?.solver_status}
          runCode={planResult?.run_code}
        />

        {/* KPI Summary Cards */}
        <KPISummary metrics={planResult?.metrics} loading={planMutation.isPending} />

        {/* Charts & Early Alerts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <InventoryChart
              warehouses={overview?.warehouses || []}
              products={overview?.products || []}
            />
          </div>
          <div className="lg:col-span-1">
            <StockoutAlerts alerts={planResult?.stockout_risks || []} />
          </div>
        </div>

        {/* Shipments Data Table */}
        <ShipmentTable shipments={planResult?.shipments || []} />
      </main>

      <footer className="border-t border-border/40 py-4 text-center text-xs text-muted-foreground">
        StockWise AI &bull; FMCG Distribution Intelligence Engine &bull; Local-First Architecture
      </footer>
    </div>
  );
}
