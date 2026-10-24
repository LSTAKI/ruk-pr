import React from "react";
import { Boxes, Sparkles, Activity, ShieldCheck } from "lucide-react";

export function Navbar({ activeDatasetVersion }: { activeDatasetVersion?: string }) {
  return (
    <header className="border-b border-border/60 bg-card/40 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="bg-primary/20 border border-primary/40 p-2 rounded-lg text-primary">
            <Boxes className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-lg tracking-tight text-white">StockWise AI</span>
              <span className="text-[10px] bg-primary/20 text-primary border border-primary/30 px-1.5 py-0.5 rounded font-mono font-medium">
                LOCAL-FIRST
              </span>
            </div>
            <p className="text-xs text-muted-foreground hidden sm:block">
              FMCG Distribution Intelligence & Inventory Optimization
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="hidden md:flex items-center space-x-2 text-xs bg-secondary/50 border border-border px-3 py-1.5 rounded-full">
            <ShieldCheck className="h-3.5 w-3.5 text-accent" />
            <span className="text-muted-foreground">Dataset:</span>
            <span className="font-mono text-foreground font-semibold">
              {activeDatasetVersion || "v1.0-seed-42"}
            </span>
          </div>

          <div className="flex items-center space-x-1 text-xs text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2.5 py-1 rounded-full">
            <Activity className="h-3.5 w-3.5 animate-pulse" />
            <span>Solver Engine Ready</span>
          </div>
        </div>
      </div>
    </header>
  );
}
