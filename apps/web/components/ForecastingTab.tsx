"use client";

import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchProducts,
  fetchDestinations,
  fetchDemandHistory,
  generateForecast,
  evaluateForecast,
  ForecastResponse,
  ForecastEvaluationResponse,
} from "@/lib/api";
import {
  TrendingUp,
  BarChart2,
  Calendar,
  AlertCircle,
  Play,
  RefreshCw,
  Info,
  CheckCircle,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

export function ForecastingTab() {
  const [selectedProductId, setSelectedProductId] = useState<number>(1);
  const [selectedDestinationId, setSelectedDestinationId] = useState<number>(1);
  const [horizonDays, setHorizonDays] = useState<7 | 14 | 30>(7);
  const [method, setMethod] = useState<"naive" | "ewma" | "seasonal_naive">("ewma");
  const [ewmaAlpha, setEwmaAlpha] = useState<number>(0.3);

  const [forecastResult, setForecastResult] = useState<ForecastResponse | null>(null);
  const [evalResult, setEvalResult] = useState<ForecastEvaluationResponse | null>(null);

  const { data: products } = useQuery({
    queryKey: ["inventory-products"],
    queryFn: fetchProducts,
  });

  const { data: destinations } = useQuery({
    queryKey: ["inventory-destinations"],
    queryFn: fetchDestinations,
  });

  const { data: historyData } = useQuery({
    queryKey: ["demand-history", selectedProductId, selectedDestinationId],
    queryFn: () =>
      fetchDemandHistory({
        product_id: selectedProductId,
        destination_id: selectedDestinationId,
        limit: 60,
      }),
  });

  // Forecast mutation
  const forecastMutation = useMutation({
    mutationFn: () =>
      generateForecast({
        product_id: selectedProductId,
        destination_id: selectedDestinationId,
        horizon_days: horizonDays,
        method: method,
        ewma_alpha: ewmaAlpha,
      }),
    onSuccess: (data) => {
      setForecastResult(data);
    },
  });

  // Backtest evaluation mutation
  const evalMutation = useMutation({
    mutationFn: () =>
      evaluateForecast({
        product_id: selectedProductId,
        destination_id: selectedDestinationId,
        ewma_alpha: ewmaAlpha,
      }),
    onSuccess: (data) => {
      setEvalResult(data);
    },
  });

  // Prepare chart series: combine last 30 days of actual demand + forecast horizon
  const historyRecords = historyData?.records || [];
  const chartData: Array<{ date: string; actual?: number; forecast?: number }> = [];

  // Sort history ascending
  const sortedHistory = [...historyRecords].sort(
    (a, b) => new Date(a.demand_date).getTime() - new Date(b.demand_date).getTime()
  );

  for (const h of sortedHistory.slice(-30)) {
    chartData.push({
      date: new Date(h.demand_date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      actual: h.quantity_demanded,
    });
  }

  if (forecastResult && forecastResult.daily_forecasts) {
    for (const f of forecastResult.daily_forecasts) {
      chartData.push({
        date: new Date(f.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        forecast: Number(f.value.toFixed(1)),
      });
    }
  }

  const selectedProduct = products?.find((p) => p.id === selectedProductId);
  const selectedDest = destinations?.find((d) => d.id === selectedDestinationId);

  return (
    <div className="space-y-6" data-testid="demand-forecasting-tab">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-white">Demand Forecasting &amp; Backtesting Engine</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Deterministic time-series forecasting across 800 product-destination corridors using chronological evaluation
        </p>
      </div>

      {/* Disclaimers */}
      <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-3.5 text-xs text-slate-300 flex items-start space-x-3">
        <Info className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-white">Simulated Demand Disclosure:</span>
          <span className="ml-1 text-slate-300">
            Historical demand is generated using a deterministic FMCG simulator with day-of-week seasonality and Poisson daily ordering. Backtesting strictly prevents data leakage by holding out the final chronological window.
          </span>
        </div>
      </div>

      {/* Controls Form */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-4 shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Product */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Select Product</label>
            <select
              value={selectedProductId}
              onChange={(e) => setSelectedProductId(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              {products?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} - {p.name}
                </option>
              ))}
            </select>
          </div>

          {/* Destination */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Select Destination Store</label>
            <select
              value={selectedDestinationId}
              onChange={(e) => setSelectedDestinationId(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              {destinations?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code} - {d.name} ({d.city})
                </option>
              ))}
            </select>
          </div>

          {/* Method */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Forecasting Method</label>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value as any)}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="ewma">EWMA (Exponentially Weighted)</option>
              <option value="naive">Naive (Last Observed Day)</option>
              <option value="seasonal_naive">Seasonal Naive (7-Day Lag)</option>
            </select>
          </div>

          {/* Horizon */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Forecast Horizon</label>
            <select
              value={horizonDays}
              onChange={(e) => setHorizonDays(Number(e.target.value) as any)}
              className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value={7}>7 Days Ahead</option>
              <option value={14}>14 Days Ahead</option>
              <option value={30}>30 Days Ahead</option>
            </select>
          </div>
        </div>

        {method === "ewma" && (
          <div className="flex items-center space-x-4 pt-2">
            <span className="text-xs text-slate-400">EWMA Smoothing Parameter (&alpha;):</span>
            <input
              type="range"
              min="0.05"
              max="0.95"
              step="0.05"
              value={ewmaAlpha}
              onChange={(e) => setEwmaAlpha(Number(e.target.value))}
              className="w-48 accent-sky-500"
            />
            <span className="font-mono text-xs text-sky-400 font-semibold">{ewmaAlpha.toFixed(2)}</span>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
          <div className="text-xs text-slate-500">
            Series: <span className="text-slate-300 font-medium">{selectedProduct?.sku}</span> &rarr;{" "}
            <span className="text-slate-300 font-medium">{selectedDest?.code}</span>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => evalMutation.mutate()}
              disabled={evalMutation.isPending}
              className="inline-flex items-center space-x-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-3.5 py-2 rounded-lg border border-slate-700 transition-colors disabled:opacity-50"
            >
              {evalMutation.isPending ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <BarChart2 className="h-3.5 w-3.5 text-indigo-400" />
              )}
              <span>Run Backtest Evaluation</span>
            </button>

            <button
              onClick={() => forecastMutation.mutate()}
              disabled={forecastMutation.isPending}
              data-testid="generate-forecast-btn"
              className="inline-flex items-center space-x-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium px-4 py-2 rounded-lg transition-colors shadow-sm disabled:opacity-50"
            >
              {forecastMutation.isPending ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5 fill-current" />
              )}
              <span>Generate Forecast</span>
            </button>
          </div>
        </div>
      </div>

      {/* Forecast Output Summary */}
      {forecastResult && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="forecast-summary">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-xs text-slate-400">Total Horizon Demand</span>
            <div className="text-2xl font-bold text-white mt-1 font-mono">
              {forecastResult.forecasted_units.toLocaleString()} units
            </div>
            <p className="text-[11px] text-slate-500 mt-1">{forecastResult.horizon_days}-day cumulative demand</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-xs text-slate-400">Daily Mean Demand</span>
            <div className="text-2xl font-bold text-sky-400 mt-1 font-mono">
              {forecastResult.daily_mean_demand.toFixed(1)} u/day
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Average daily ordering rate</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-xs text-slate-400">Algorithm Used</span>
            <div className="text-2xl font-bold text-emerald-400 mt-1 font-mono uppercase">
              {forecastResult.method}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">{forecastResult.history_observations_used} history days used</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <span className="text-xs text-slate-400">Generated Timestamp</span>
            <div className="text-sm font-semibold text-slate-200 mt-2">
              {new Date(forecastResult.generated_at).toLocaleTimeString()}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Status: Ready for optimizer</p>
          </div>
        </div>
      )}

      {/* Interactive Demand Trajectory Chart */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-white">Historical Demand vs. Forecast Trajectory</h3>
            <p className="text-xs text-slate-400">
              Daily actuals (last 30 days) followed by forward projection
            </p>
          </div>
          <span className="text-xs font-mono bg-slate-800 px-2 py-0.5 rounded text-slate-300">
            {chartData.length} data points
          </span>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickLine={false} />
              <YAxis stroke="#64748b" fontSize={11} tickLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#020617",
                  borderColor: "#1e293b",
                  borderRadius: "8px",
                  fontSize: "12px",
                  color: "#f8fafc",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }} />
              <Line
                type="monotone"
                dataKey="actual"
                name="Historical Demand (Units)"
                stroke="#94a3b8"
                strokeWidth={1.5}
                dot={{ r: 2 }}
                activeDot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="forecast"
                name="Forecast Demand (Units)"
                stroke="#38bdf8"
                strokeWidth={2.5}
                strokeDasharray="4 2"
                dot={{ r: 3, fill: "#38bdf8" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Backtesting Evaluation Section */}
      {evalResult && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-4" data-testid="backtest-results">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Backtesting Evaluation Results (Holdout Validation)</h3>
              <p className="text-xs text-slate-400">
                Evaluation across {evalResult.n_series_evaluated} corridor series on holdout test partition
              </p>
            </div>
            <span className="text-xs text-slate-400 font-mono">
              {evalResult.total_observations_evaluated} observations evaluated
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {Object.entries(evalResult.aggregate).map(([mName, agg]) => (
              <div key={mName} className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-xs uppercase font-semibold text-sky-400">{mName}</span>
                  <span className="text-[10px] text-slate-500">{agg.series_with_method} series</span>
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Mean MAE:</span>
                    <span className="font-mono text-white font-medium">
                      {agg.mae_mean !== null && agg.mae_mean !== undefined ? agg.mae_mean.toFixed(2) : "—"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Mean WAPE:</span>
                    <span className="font-mono text-emerald-400 font-medium">
                      {agg.wape_mean_pct !== null && agg.wape_mean_pct !== undefined
                        ? `${agg.wape_mean_pct.toFixed(1)}%`
                        : "Unavailable"}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {evalResult.caveats && evalResult.caveats.length > 0 && (
            <div className="text-[11px] text-slate-500 border-t border-slate-800/80 pt-2 space-y-0.5">
              {evalResult.caveats.map((c, i) => (
                <p key={i}>&bull; {c}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
