import React from "react";
import { Truck, DollarSign, AlertTriangle, ShieldCheck } from "lucide-react";
import { PlanMetrics } from "@/lib/api";

interface KPISummaryProps {
  metrics?: PlanMetrics;
  loading?: boolean;
}

export function KPISummary({ metrics, loading }: { metrics?: PlanMetrics; loading?: boolean }) {
  const cards = [
    {
      title: "Recommended Shipments",
      value: metrics ? `${metrics.total_shipped_units.toLocaleString()} units` : "—",
      subtext: "Across regional warehouse network",
      icon: Truck,
      color: "text-sky-400",
      bg: "bg-sky-500/10 border-sky-500/20",
      testId: "kpi-shipments",
    },
    {
      title: "Optimized Freight Cost",
      value: metrics ? `$${metrics.total_transport_cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "—",
      subtext: "Minimizing mileage & transit cost",
      icon: DollarSign,
      color: "text-emerald-400",
      bg: "bg-emerald-500/10 border-emerald-500/20",
      testId: "kpi-cost",
    },
    {
      title: "Expiry Wastage Risk",
      value: metrics ? `${metrics.avg_expiry_risk_pct}%` : "—",
      subtext: "Prioritizing near-dated stock (FEFO)",
      icon: ShieldCheck,
      color: "text-amber-400",
      bg: "bg-amber-500/10 border-amber-500/20",
      testId: "kpi-expiry",
    },
    {
      title: "Destinations at Stockout Risk",
      value: metrics ? `${metrics.destinations_at_risk} stores` : "—",
      subtext: `${metrics ? metrics.stockouts_prevented : 0} stockouts mitigated`,
      icon: AlertTriangle,
      color: "text-rose-400",
      bg: "bg-rose-500/10 border-rose-500/20",
      testId: "kpi-stockout",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <div
            key={c.title}
            data-testid={c.testId}
            className="rounded-xl border border-border bg-card/60 backdrop-blur-sm p-4 flex flex-col justify-between hover:border-border/80 transition-all shadow-sm"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{c.title}</span>
              <div className={`p-2 rounded-lg border ${c.bg}`}>
                <Icon className={`h-4 w-4 ${c.color}`} />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold tracking-tight text-white">
                {loading ? <span className="animate-pulse">Loading...</span> : c.value}
              </div>
              <p className="text-xs text-muted-foreground mt-1">{c.subtext}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
