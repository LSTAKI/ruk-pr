import React from "react";
import { AlertCircle, Clock } from "lucide-react";
import { StockoutAlert } from "@/lib/api";

interface StockoutAlertsProps {
  alerts: StockoutAlert[];
}

export function StockoutAlerts({ alerts }: StockoutAlertsProps) {
  return (
    <div className="rounded-xl border border-border bg-card/60 backdrop-blur-sm p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-white">Stockout Risk Detection</h3>
          <p className="text-xs text-muted-foreground">Destinations requiring immediate replenishment</p>
        </div>
        <span className="text-xs bg-rose-500/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 rounded-full font-mono font-medium">
          {alerts.length} Critical
        </span>
      </div>

      <div className="space-y-2.5 max-h-[320px] overflow-y-auto pr-1">
        {alerts.length === 0 ? (
          <div className="text-xs text-muted-foreground py-8 text-center">
            No active stockout risks detected across destination network.
          </div>
        ) : (
          alerts.map((a, idx) => (
            <div
              key={`${a.destination_code}-${a.product_sku}-${idx}`}
              className="flex items-center justify-between p-3 rounded-lg border border-border/80 bg-secondary/30 hover:border-border transition-colors text-xs"
            >
              <div className="flex items-start space-x-2.5">
                <AlertCircle
                  className={`h-4 w-4 shrink-0 mt-0.5 ${
                    a.risk_level === "HIGH" ? "text-rose-400" : "text-amber-400"
                  }`}
                />
                <div>
                  <div className="font-medium text-white">{a.destination_name}</div>
                  <div className="text-[11px] text-muted-foreground">
                    Product: <span className="text-foreground font-mono">{a.product_sku}</span>
                  </div>
                </div>
              </div>

              <div className="text-right shrink-0">
                <div className="flex items-center space-x-1 justify-end font-mono">
                  <Clock className="h-3 w-3 text-muted-foreground" />
                  <span
                    className={`font-semibold ${
                      a.current_inventory_days <= 1.0 ? "text-rose-400" : "text-amber-400"
                    }`}
                  >
                    {a.current_inventory_days} days
                  </span>
                </div>
                <div className="text-[10px] text-muted-foreground">
                  Demand: {a.forecasted_daily_demand} u/day
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
