"use client";

import React, { useEffect, useState } from "react";
import {
  Boxes,
  Activity,
  ShieldCheck,
  LayoutDashboard,
  Package,
  TrendingUp,
  RotateCcw,
  Cpu,
  GitCompare,
  History,
} from "lucide-react";
import { fetchHealth, HealthStatus } from "@/lib/api";

export type TabType =
  | "overview"
  | "inventory"
  | "forecasting"
  | "replenishment"
  | "optimization"
  | "scenarios"
  | "history";

interface NavbarProps {
  activeTab: TabType;
  onSelectTab: (tab: TabType) => void;
  activeDatasetVersion?: string;
}

export function Navbar({ activeTab, onSelectTab, activeDatasetVersion }: NavbarProps) {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    let isMounted = true;
    fetchHealth()
      .then((data) => {
        if (isMounted) {
          setHealth(data);
          setHealthError(false);
        }
      })
      .catch(() => {
        if (isMounted) setHealthError(true);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const navItems: { id: TabType; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: "overview", label: "Overview", icon: LayoutDashboard },
    { id: "inventory", label: "Inventory Explorer", icon: Package },
    { id: "forecasting", label: "Demand Forecast", icon: TrendingUp },
    { id: "replenishment", label: "Replenishment", icon: RotateCcw },
    { id: "optimization", label: "Optimizer Planner", icon: Cpu },
    { id: "scenarios", label: "Scenario Compare", icon: GitCompare },
    { id: "history", label: "Planning History", icon: History },
  ];

  return (
    <header className="border-b border-border/80 bg-slate-950/90 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="h-16 flex items-center justify-between gap-4">
          {/* Brand */}
          <div className="flex items-center space-x-3 shrink-0">
            <div className="bg-sky-500/10 border border-sky-500/30 p-2 rounded-lg text-sky-400">
              <Boxes className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-base tracking-tight text-white">StockWise AI</span>
                <span className="text-[10px] bg-sky-950/80 text-sky-400 border border-sky-800/60 px-1.5 py-0.5 rounded font-mono font-medium">
                  LOCAL-FIRST
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">
                FMCG Distribution Intelligence &amp; Multi-Echelon Optimizer
              </p>
            </div>
          </div>

          {/* Top-level Badges */}
          <div className="flex items-center space-x-3 text-xs">
            {/* Dataset Badge */}
            <div className="hidden lg:flex items-center space-x-1.5 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-md text-[11px]">
              <ShieldCheck className="h-3.5 w-3.5 text-amber-400 shrink-0" />
              <span className="text-slate-400">Data:</span>
              <span className="font-mono text-slate-200 font-medium">
                {activeDatasetVersion || health?.active_dataset_version || "Simulated FMCG v1.0"}
              </span>
              <span className="text-[10px] text-amber-400/90 font-mono">(Simulated)</span>
            </div>

            {/* Health Status */}
            <div
              className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-[11px] border ${
                healthError
                  ? "bg-rose-950/50 text-rose-400 border-rose-800/50"
                  : "bg-emerald-950/50 text-emerald-400 border-emerald-800/50"
              }`}
            >
              <Activity className={`h-3.5 w-3.5 ${healthError ? "" : "animate-pulse"}`} />
              <span>{healthError ? "Backend Disconnected" : "Engine Online"}</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex space-x-1 overflow-x-auto pb-2 pt-1 border-t border-slate-900 scrollbar-none" aria-label="Tabs">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                data-testid={`nav-tab-${item.id}`}
                className={`flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                  isActive
                    ? "bg-sky-500/15 text-sky-300 border border-sky-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent"
                }`}
              >
                <Icon className={`h-3.5 w-3.5 ${isActive ? "text-sky-400" : "text-slate-500"}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
