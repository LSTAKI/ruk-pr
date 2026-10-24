"use client";

import React from "react";
import { Play, Sliders, RefreshCw } from "lucide-react";

interface OptimizationControlsProps {
  onRunPlan: () => void;
  loading: boolean;
  horizonDays: number;
  setHorizonDays: (days: number) => void;
  solverStatus?: string;
  runCode?: string;
}

export function OptimizationControls({
  onRunPlan,
  loading,
  horizonDays,
  setHorizonDays,
  solverStatus,
  runCode,
}: OptimizationControlsProps) {
  return (
    <div className="rounded-xl border border-border bg-card/60 backdrop-blur-sm p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
      <div className="flex items-center space-x-3">
        <div className="p-2 bg-primary/10 border border-primary/20 rounded-lg text-primary">
          <Sliders className="h-4 w-4" />
        </div>
        <div>
          <div className="text-xs font-semibold text-white">Optimization Parameters</div>
          <p className="text-[11px] text-muted-foreground">
            Linear solver multi-echelon model with shelf-life expiry penalization
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center space-x-2 text-xs">
          <span className="text-muted-foreground">Horizon:</span>
          <select
            value={horizonDays}
            onChange={(e) => setHorizonDays(Number(e.target.value))}
            className="bg-secondary/70 border border-border text-foreground rounded-lg px-2.5 py-1 text-xs focus:ring-1 focus:ring-primary focus:outline-none"
          >
            <option value={3}>3 Days</option>
            <option value={7}>7 Days (Default)</option>
            <option value={14}>14 Days</option>
          </select>
        </div>

        {runCode && (
          <div className="hidden lg:flex items-center space-x-1.5 text-[11px] text-muted-foreground bg-secondary/50 border border-border px-2.5 py-1 rounded-md">
            <span>Status:</span>
            <span className="font-mono text-emerald-400 font-semibold">{solverStatus || "OPTIMAL"}</span>
          </div>
        )}

        <button
          onClick={onRunPlan}
          disabled={loading}
          data-testid="run-optimizer-btn"
          className="flex items-center space-x-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50"
        >
          {loading ? (
            <>
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              <span>Solving Allocation...</span>
            </>
          ) : (
            <>
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>Run Local Optimizer</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
