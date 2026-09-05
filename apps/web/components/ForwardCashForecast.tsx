"use client";

import {
  CheckCircle2,
  ChevronRight,
  Clock,
  Table as TableIcon,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AmountDisplay } from "@/components/AmountDisplay";
import type { CashForecastDay, CashForecastResponse } from "@/lib/api";
import { formatInteger, formatPaise } from "@/lib/format";

interface ForwardCashForecastProps {
  forecast: CashForecastResponse;
  selectedDay: number | null;
  onSelectDay: (dayOffset: number | null) => void;
}

export function ForwardCashForecast({
  forecast,
  selectedDay,
  onSelectDay,
}: ForwardCashForecastProps) {
  const [viewMode, setViewMode] = useState<"chart" | "table">("chart");

  const chartData = forecast.days.map((day) => ({
    label: day.label,
    date: day.date,
    shortDate: day.date.slice(5),
    inflow: day.expected_inflow_paise / 100,
    inflowPaise: day.expected_inflow_paise,
    closing: day.closing_cash_paise / 100,
    closingPaise: day.closing_cash_paise,
    openingPaise: day.opening_cash_paise,
    isBankingDay: day.is_banking_day,
    caseCount: day.case_count,
    dayOffset: day.day_offset,
  }));

  return (
    <section className="panel min-w-0 overflow-hidden" data-testid="forward-cash-forecast">
      <div className="panel-header flex-wrap items-center justify-between gap-4 bg-[#f8fafc]">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <span className="eyebrow mb-0 text-[#0c44ac]">Liquidity Projection</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-[#ecfdf5] border border-[#a7f3d0] px-2 py-0.5 text-[0.62rem] font-bold text-[#065f46]">
              <CheckCircle2 size={11} /> T+0 to T+7 schedule
            </span>
          </div>
          <h2 className="panel-title text-[1.05rem] font-bold">Forward Cash Forecast</h2>
          <p className="panel-copy">
            As of {forecast.as_of_date}. Expected batch inflows under the configured settlement policy; excludes operating expenses and unmodeled cash flows.
          </p>
          <p className="mb-0 mt-1 text-[0.66rem] text-[#64748b]">
            Computation version: execution {forecast.execution_revision}, review {forecast.review_revision}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center rounded-[6px] border border-[#e2e8f0] bg-[#f1f5f9] p-0.5 text-[0.7rem] font-semibold">
            <button
              className={`flex items-center gap-1 rounded-[4px] px-2.5 py-1 transition-colors ${
                viewMode === "chart"
                  ? "bg-white font-bold text-[#081225] shadow-xs"
                  : "text-[#64748b] hover:text-[#081225]"
              }`}
              onClick={() => setViewMode("chart")}
              type="button"
            >
              <TrendingUp size={13} /> Visual Timeline
            </button>
            <button
              className={`flex items-center gap-1 rounded-[4px] px-2.5 py-1 transition-colors ${
                viewMode === "table"
                  ? "bg-white font-bold text-[#081225] shadow-xs"
                  : "text-[#64748b] hover:text-[#081225]"
              }`}
              onClick={() => setViewMode("table")}
              type="button"
            >
              <TableIcon size={13} /> Schedule Table
            </button>
          </div>

          <div className="flex items-center gap-2 rounded-[6px] border border-[#a7f3d0] bg-[#ecfdf5] px-3 py-1.5 text-right">
            <div>
              <p className="m-0 text-[0.62rem] font-bold uppercase tracking-wider text-[#065f46]">
                Projected inflows through T+7
              </p>
              <AmountDisplay
                className="text-[0.92rem] font-extrabold text-[#059669]"
                paise={forecast.total_projected_inflow_paise}
              />
            </div>
          </div>
        </div>
      </div>

      <p className="m-0 border-b px-4 py-3 text-xs text-slate-600">Overdue expected receipts: {formatPaise(forecast.overdue_inflow_paise)} · Receipts without a reliable date: {formatPaise(forecast.undated_inflow_paise)}. These amounts remain separately disclosed.</p>
      {/* Day Selector Ribbon */}
      <div className="flex items-center gap-1.5 overflow-x-auto border-b border-[#e2e8f0] bg-[#f8fafc] p-2.5">
        <button
          className={`shrink-0 rounded-[6px] px-3 py-1.5 text-[0.72rem] font-bold transition-[background-color,border-color,color] ${
            selectedDay === null
              ? "border border-[#059669] bg-[#ecfdf5] text-[#059669]"
              : "border border-[#e2e8f0] bg-white text-[#475569] hover:bg-[#f1f5f9]"
          }`}
          onClick={() => onSelectDay(null)}
          type="button"
        >
          All Horizon (T+0 – T+7)
        </button>

        {forecast.days.map((day) => {
          const isSelected = selectedDay === day.day_offset;
          const hasInflow = day.expected_inflow_paise > 0;
          return (
            <button
              className={`flex shrink-0 items-center gap-1.5 rounded-[6px] px-2.5 py-1 text-[0.72rem] transition-[background-color,border-color,color] ${
                isSelected
                  ? "border border-[#059669] bg-[#ecfdf5] font-bold text-[#059669]"
                  : "border border-[#e2e8f0] bg-white text-[#475569] hover:bg-[#f1f5f9]"
              }`}
              key={day.day_offset}
              onClick={() => onSelectDay(isSelected ? null : day.day_offset)}
              title={`${day.label} (${day.date}): ${formatPaise(day.expected_inflow_paise)} expected inflow`}
              type="button"
            >
              <span>{day.label}</span>
              {hasInflow ? (
                <span className="rounded-[4px] bg-[#ecfdf5] border border-[#a7f3d0] px-1.5 py-0.2 text-[0.64rem] font-extrabold text-[#059669]">
                  +{formatPaise(day.expected_inflow_paise)}
                </span>
              ) : (
                <span className="text-[0.64rem] text-[#94a3b8]">₹0</span>
              )}
            </button>
          );
        })}
      </div>

      {/* View Body: Chart or Table */}
      <div className="p-4">
        {viewMode === "chart" ? (
          <div className="space-y-3">
            <div className="h-[280px] w-full min-w-0">
              <ResponsiveContainer height="100%" width="100%">
                <ComposedChart data={chartData} margin={{ top: 12, right: 24, left: 16, bottom: 8 }}>
                  <defs>
                    <linearGradient id="closingCashGrad" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="5%" stopColor="#0c44ac" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#0c44ac" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis dataKey="shortDate" stroke="#64748b" tick={{ fontSize: 11 }} />
                  <YAxis
                    allowDecimals={false}
                    stroke="#64748b"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                    yAxisId="left"
                  />
                  <YAxis
                    allowDecimals={false}
                    orientation="right"
                    stroke="#0c44ac"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                    yAxisId="right"
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const item = payload[0].payload as (typeof chartData)[number];
                      return (
                        <div className="rounded-[8px] border border-[#e2e8f0] bg-white p-3 text-[0.72rem] shadow-lg">
                          <p className="mb-1 font-bold text-[#081225]">
                            {item.label} · <span className="font-mono text-[#64748b]">{item.date}</span>
                          </p>
                          <p className="mb-2 text-[0.66rem] font-semibold text-[#64748b]">
                            {item.isBankingDay ? "✓ Policy banking day" : "⚠ Weekend / Bank Holiday"}
                          </p>
                          <div className="space-y-1 divide-y divide-[#f1f5f9]">
                            <div className="flex items-center justify-between gap-4 pt-1">
                              <span className="text-[#64748b]">Projected Inflow:</span>
                              <strong className="text-[#059669]">
                                +{formatPaise(item.inflowPaise)}
                              </strong>
                            </div>
                            <div className="flex items-center justify-between gap-4 pt-1">
                              <span className="text-[#64748b]">Projected batch receipts:</span>
                              <strong className="text-[#0c44ac]">
                                {formatPaise(item.closingPaise)}
                              </strong>
                            </div>
                            <div className="flex items-center justify-between gap-4 pt-1 text-[0.66rem] text-[#64748b]">
                              <span>Contributing Cases:</span>
                              <strong>{item.caseCount} cases</strong>
                            </div>
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Bar
                    dataKey="inflow"
                    fill="#059669"
                    name="Daily Inflow"
                    radius={[4, 4, 0, 0]}
                    yAxisId="left"
                  />
                  <Area
                    dataKey="closing"
                    fill="url(#closingCashGrad)"
                    name="Projected Safe Cash"
                    stroke="#0c44ac"
                    strokeWidth={2.5}
                    type="monotone"
                    yAxisId="right"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 text-[0.7rem] text-[#64748b]">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-[2px] bg-[#059669]" />
                  Daily Inflow (Left Axis)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-[2px] bg-[#0c44ac]" />
                  Cumulative Closing Cash (Right Axis)
                </span>
              </div>
              <span className="italic text-[#64748b]">
                Click any day above or below to filter contributing cases
              </span>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[0.74rem]">
              <thead>
                <tr className="border-b border-[#e2e8f0] bg-[#f8fafc] text-[0.68rem] font-bold text-[#475569]">
                  <th className="px-3 py-2.5">Horizon</th>
                  <th className="px-3 py-2.5">Date</th>
                  <th className="px-3 py-2.5">Calendar Status</th>
                  <th className="px-3 py-2.5 text-right">Opening Cash</th>
                  <th className="px-3 py-2.5 text-right">Expected Inflow</th>
                  <th className="px-3 py-2.5 text-right">Closing Projected Cash</th>
                  <th className="px-3 py-2.5 text-center">Cases</th>
                  <th className="px-3 py-2.5">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f1f5f9]">
                {forecast.days.map((day: CashForecastDay) => {
                  const isSelected = selectedDay === day.day_offset;
                  return (
                    <tr
                      className={`transition-colors hover:bg-[#f8fafc] ${
                        isSelected ? "bg-[#eff6ff]" : ""
                      }`}
                      key={day.day_offset}
                    >
                      <td className="px-3 py-2.5 font-bold text-[#0f172a]">
                        {day.label}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[#64748b]">
                        {day.date}
                      </td>
                      <td className="px-3 py-2.5">
                        {day.is_banking_day ? (
                          <span className="inline-flex items-center gap-1 rounded border border-[#a7f3d0] bg-[#ecfdf5] px-2 py-0.5 text-[0.64rem] font-bold text-[#065f46]">
                            Banking Day
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded border border-[#fecdd3] bg-[#fff1f2] px-2 py-0.5 text-[0.64rem] font-bold text-[#e11d48]">
                            Holiday / Weekend
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right font-medium text-[#475569]">
                        <AmountDisplay paise={day.opening_cash_paise} />
                      </td>
                      <td className="px-3 py-2.5 text-right font-extrabold text-[#059669]">
                        {day.expected_inflow_paise > 0 ? (
                          <>+{formatPaise(day.expected_inflow_paise)}</>
                        ) : (
                          <span className="text-[#94a3b8]">₹0.00</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right font-extrabold text-[#0c44ac]">
                        <AmountDisplay paise={day.closing_cash_paise} />
                      </td>
                      <td className="px-3 py-2.5 text-center font-semibold text-[#0f172a]">
                        {formatInteger(day.case_count)}
                      </td>
                      <td className="px-3 py-2.5">
                        <button
                          className="inline-flex items-center gap-1 text-[0.68rem] font-bold text-[#0c44ac] hover:text-[#09368b] hover:underline"
                          onClick={() => onSelectDay(isSelected ? null : day.day_offset)}
                          type="button"
                        >
                          {isSelected ? "Clear Filter" : "Filter Cases"}{" "}
                          <ChevronRight size={11} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 flex items-center gap-2 rounded-[6px] border border-[#e2e8f0] bg-[#f8fafc] p-2.5 text-[0.68rem] text-[#475569]">
          <Clock aria-hidden="true" className="shrink-0 text-[#0c44ac]" size={14} />
          <span>
            <strong>Settlement policy:</strong> Inflows follow the run’s configured settlement dates and holiday calendar. Expected receipts are projections, not confirmed bank cash.
          </span>
        </div>
      </div>
    </section>
  );
}
