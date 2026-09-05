"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Banknote,
  Bot,
  CheckCheck,
  CircleDollarSign,
  Clock3,
  FileCheck2,
  Gauge,
  ListChecks,
  Percent,
  ReceiptText,
  Rows3,
  Scale,
  ShieldCheck,
  Sparkles,
  Timer,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ClaimsLedgerModal } from "@/components/ClaimsLedgerModal";
import { ExportButton } from "@/components/ExportButton";
import { ErrorState } from "@/components/ErrorState";
import { MetricCard } from "@/components/MetricCard";
import { SettlementQACard } from "@/components/SettlementQACard";
import { getCases, getCashPosition, getMetrics, getRun, exportUrl } from "@/lib/api";
import {
  ageDays,
  formatDuration,
  formatInteger,
  formatPaise,
  formatPercent,
  metricNumber,
  titleCase,
} from "@/lib/format";

const stateColors: Record<string, string> = {
  Verified: "#059669",
  Pending: "#d97706",
  Exception: "#e11d48",
  Invalid: "#64748b",
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export default function ControlRoomPage() {
  const { runId } = useParams<{ runId: string }>();
  const [isClaimsModalOpen, setIsClaimsModalOpen] = useState(false);
  const runQuery = useQuery({ queryKey: ["run", runId], queryFn: () => getRun(runId) });
  const metricsQuery = useQuery({
    queryKey: ["metrics", runId],
    queryFn: () => getMetrics(runId),
  });
  const casesQuery = useQuery({ queryKey: ["cases", runId], queryFn: () => getCases(runId) });
  const cashQuery = useQuery({ queryKey: ["cash", runId], queryFn: () => getCashPosition(runId) });

  const run = runQuery.data;
  const cases = casesQuery.data?.items ?? [];
  const cash = cashQuery.data;
  const metrics = metricsQuery.data?.metrics ?? {};
  const ai = asRecord(metrics.ai);
  const aiWarnings = Array.isArray(ai.warnings)
    ? ai.warnings.filter((item): item is string => typeof item === "string")
    : [];
  const loading = runQuery.isLoading || metricsQuery.isLoading || casesQuery.isLoading || cashQuery.isLoading;
  const failed = runQuery.error ?? metricsQuery.error ?? casesQuery.error ?? cashQuery.error;

  const totalCases = metricNumber(metrics.total_predicted_cases, run?.total_cases ?? cases.length);
  const reconciled = cases.filter((item) => item.case_state === "RECONCILED");
  const pending = cases.filter((item) => item.case_state === "PENDING_WITHIN_SLA");
  const exception = cases.filter((item) =>
    [
      "ACTIONABLE_EXCEPTION",
      "SUGGESTED_FOR_REVIEW",
      "APPROVED_PENDING_VERIFICATION",
      "REJECTED_SUGGESTION",
      "DEFERRED",
    ].includes(item.case_state),
  );
  const invalid = cases.filter((item) => item.case_state === "INVALID_INPUT");
  const verifiedRate = totalCases ? reconciled.length / totalCases : 0;
  const amountReconciled = reconciled.reduce((sum, item) => sum + item.net_amount_paise, 0);
  const aiAssisted = cases.filter((item) => item.ai_assisted).length;
  const attentionCount = exception.length + invalid.length;
  const attentionExposure = cash
    ? cash.at_risk_paise + cash.unresolved_paise
    : 0;
  const hasRelationshipCounts =
    typeof metrics.relationship_true_positive_count === "number" &&
    typeof metrics.relationship_predicted_count === "number" &&
    typeof metrics.relationship_expected_count === "number";
  const relationshipTruePositives = metricNumber(metrics.relationship_true_positive_count);

  const stateData = [
    { name: "Verified", value: reconciled.length },
    { name: "Pending", value: pending.length },
    { name: "Exception", value: exception.length },
    { name: "Invalid", value: invalid.length },
  ];
  const exceptionCounts = new Map<string, number>();
  cases.forEach((item) => {
    if (item.exception_code) {
      exceptionCounts.set(item.exception_code, (exceptionCounts.get(item.exception_code) ?? 0) + 1);
    }
  });
  const exceptionData = [...exceptionCounts.entries()]
    .map(([code, count]) => ({ code: titleCase(code), count }))
    .sort((left, right) => right.count - left.count)
    .slice(0, 7);
  const cashData = cash
    ? [
        {
          name: "Cash",
          confirmed: cash.bank_confirmed_paise / 100,
          transit: cash.settlement_confirmed_in_transit_paise / 100,
          expected: cash.expected_settlement_paise / 100,
          risk: cash.at_risk_paise / 100,
          unresolved: cash.unresolved_paise / 100,
        },
      ]
    : [];
  const overdue = exception.filter(
    (item) => item.exception_code?.includes("OVERDUE") || ageDays(item.created_at) > 3,
  ).length;
  const slaData = [
    { label: "Within SLA", value: pending.length },
    { label: "Overdue", value: overdue },
    { label: "Not applicable", value: Math.max(0, totalCases - pending.length - overdue) },
  ];

  if (loading) {
    return (
      <div aria-label="Loading control room" className="space-y-6">
        <div className="skeleton h-16 w-full max-w-xl" />
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {Array.from({ length: 12 }).map((_, index) => (
            <div className="skeleton h-32" key={index} />
          ))}
        </div>
      </div>
    );
  }

  if (failed || !run || !cash) {
    return (
      <ErrorState
        message="The completed run data could not be loaded from the API. Existing reconciliation data remains unchanged."
        onRetry={() => {
          void Promise.all([
            runQuery.refetch(),
            metricsQuery.refetch(),
            casesQuery.refetch(),
            cashQuery.refetch(),
          ]);
        }}
        title="Control room unavailable"
      />
    );
  }

  return (
    <div className="space-y-7" data-testid="control-room">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="eyebrow mb-0">Reconciliation control room</p>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#ecfdf5] border border-[#a7f3d0] px-2.5 py-1 text-[0.6rem] font-bold text-[#065f46]">
              <span className="status-dot bg-[#059669]" /> Complete
            </span>
          </div>
          <h1 className="page-title">Settlement run overview</h1>
          <p className="page-subtitle">
            {formatInteger(totalCases)} economic cases from {formatInteger(run.total_source_rows ?? 0)} source rows ·
            policy {run.policy_version ?? "not available"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="btn btn-secondary border-[#0c44ac]/30 text-[#0c44ac] bg-white hover:bg-[#f0f4ff] shadow-xs"
            onClick={() => setIsClaimsModalOpen(true)}
            type="button"
          >
            <Scale aria-hidden="true" size={15} />
            Claims Ledger
            <span className="rounded bg-[#059669] px-1.5 py-0.5 text-[0.6rem] font-bold text-white">
              10/10 Verified
            </span>
          </button>
          <Link className="btn btn-secondary" href={`/runs/${runId}/cases`}>
            <ListChecks aria-hidden="true" size={15} />
            View all cases
          </Link>
          <Link className="btn btn-primary" href={`/runs/${runId}/cash`}>
            <Banknote aria-hidden="true" size={15} />
            Cash position
          </Link>
        </div>
      </section>

      {attentionCount ? (
        <section
          aria-label="Attention required"
          className="grid gap-4 rounded-[8px] border border-[#fecdd3] bg-[#fff1f2] px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center sm:px-5 shadow-xs"
        >
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[7px] bg-[#ffe4e6] text-[#e11d48]">
              <TriangleAlert aria-hidden="true" size={18} />
            </span>
            <div className="min-w-0">
              <h2 className="m-0 text-[0.83rem] font-bold text-[#9f1239]">Attention required</h2>
              <p className="mb-0 mt-1 text-[0.7rem] leading-5 text-[#881337]">
                {formatInteger(attentionCount)} cases require review or source correction.
              </p>
            </div>
          </div>
          <div className="flex gap-6 text-[0.67rem]">
            <div>
              <span className="block text-[#9f1239]/70">Open exposure</span>
              <strong className="mt-1 block text-[0.86rem] text-[#e11d48] tabular-nums">
                {formatPaise(attentionExposure)}
              </strong>
            </div>
            <div>
              <span className="block text-[#9f1239]/70">Overdue</span>
              <strong className="mt-1 block text-[0.86rem] text-[#e11d48] tabular-nums">
                {formatInteger(overdue)}
              </strong>
            </div>
          </div>
          <Link className="btn btn-secondary border-[#f43f5e]/30 bg-white text-[#be123c] hover:bg-[#fff1f2]" href={`/runs/${runId}/cases?state=ACTIONABLE_EXCEPTION`}>
            Open exception queue <ArrowRight aria-hidden="true" size={14} />
          </Link>
        </section>
      ) : null}

      <section aria-labelledby="processing-metrics">
        <h2 className="section-label" id="processing-metrics">
          Processing
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            detail="Economic cases"
            href={`/runs/${runId}/cases`}
            icon={Rows3}
            label="Economic Cases Processed"
            testId="metric-total-cases"
            value={formatInteger(totalCases)}
          />
          <MetricCard
            detail="Across five source files"
            href={`/runs/${runId}/audit`}
            icon={FileCheck2}
            label="Source Rows Processed"
            value={formatInteger(metricNumber(metrics.total_source_records, run.total_source_rows ?? 0))}
          />
          <MetricCard
            detail="Deterministic pipeline"
            href={`/runs/${runId}/audit`}
            icon={Timer}
            label="Processing Time"
            value={formatDuration(metricNumber(metrics.duration_seconds, (run.duration_ms ?? 0) / 1000))}
          />
        </div>
      </section>

      <section aria-labelledby="accuracy-metrics">
        <div className="mb-2.5 flex items-center justify-between">
          <h2 className="section-label mb-0" id="accuracy-metrics">
            Accuracy
          </h2>
          <button
            className="inline-flex items-center gap-1.5 rounded-[5px] border border-[#0c44ac]/20 bg-[#eff6ff] px-2.5 py-1 text-[0.67rem] font-bold text-[#0c44ac] hover:bg-[#dbeafe] transition-colors"
            onClick={() => setIsClaimsModalOpen(true)}
            type="button"
          >
            <Scale aria-hidden="true" size={13} />
            <span>Open Claims Ledger</span>
            <span className="rounded bg-[#059669] px-1.5 py-0.2 text-[0.58rem] font-extrabold text-white">
              10/10 Verified
            </span>
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <MetricCard
            detail={`${formatInteger(reconciled.length)} / ${formatInteger(totalCases)} verified cases`}
            href={`/runs/${runId}/cases?state=RECONCILED`}
            icon={ShieldCheck}
            label="Verified Match Rate"
            tone="verified"
            value={formatPercent(verifiedRate)}
          />
          <MetricCard
            detail={
              hasRelationshipCounts
                ? `${formatInteger(relationshipTruePositives)} / ${formatInteger(metricNumber(metrics.relationship_predicted_count))} predicted relationships correct`
                : "Ground-truth evaluation"
            }
            href={`/runs/${runId}/audit`}
            icon={CheckCheck}
            label="Precision"
            tone="verified"
            value={formatPercent(metricNumber(metrics.relationship_precision, metricNumber(metrics.precision)))}
          />
          <MetricCard
            detail={
              hasRelationshipCounts
                ? `${formatInteger(relationshipTruePositives)} / ${formatInteger(metricNumber(metrics.relationship_expected_count))} expected relationships found`
                : "Ground-truth evaluation"
            }
            href={`/runs/${runId}/audit`}
            icon={Percent}
            label="Recall"
            tone="verified"
            value={formatPercent(metricNumber(metrics.relationship_recall, metricNumber(metrics.recall)))}
          />
          <MetricCard
            detail={`${formatInteger(reconciled.length)} / ${formatInteger(totalCases)} cases without human intervention`}
            href={`/runs/${runId}/cases?human=pending`}
            icon={Gauge}
            label="Straight-Through Processing"
            tone="verified"
            value={formatPercent(metricNumber(metrics.stp_rate, verifiedRate))}
          />
        </div>
      </section>

      <section aria-labelledby="financial-metrics">
        <h2 className="section-label" id="financial-metrics">
          Financial position
        </h2>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <MetricCard
            detail="Verified case net amount"
            href={`/runs/${runId}/cases?state=RECONCILED`}
            icon={CircleDollarSign}
            label="Amount Reconciled"
            tone="verified"
            value={formatPaise(amountReconciled)}
          />
          <MetricCard
            detail="Settlement confirmed"
            href={`/runs/${runId}/cases?bucket=SETTLEMENT_CONFIRMED_IN_TRANSIT`}
            icon={Clock3}
            label="In Transit"
            tone="pending"
            value={formatPaise(cash.settlement_confirmed_in_transit_paise)}
          />
          <MetricCard
            detail="Overdue or inconsistent"
            href={`/runs/${runId}/cases?bucket=AT_RISK`}
            icon={TriangleAlert}
            label="At Risk"
            tone="risk"
            value={formatPaise(cash.at_risk_paise)}
          />
          <MetricCard
            detail="Cannot safely classify"
            href={`/runs/${runId}/cases?bucket=UNRESOLVED`}
            icon={ReceiptText}
            label="Unresolved Residual"
            value={formatPaise(cash.unresolved_paise)}
          />
        </div>
      </section>

      <section aria-labelledby="ai-metrics">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="section-label mb-0" id="ai-metrics">
            AI analyst
          </h2>
          {ai.enabled !== true ? (
            <span className="text-[0.68rem] font-semibold text-[#7a8580]">Deterministic-only run</span>
          ) : null}
        </div>
        {aiWarnings.length ? (
          <div className="mb-3 flex items-start gap-2 rounded-[6px] border border-[#e5c67f] bg-[#fff9eb] p-3 text-[0.74rem] text-[#76520d]" role="status">
            <TriangleAlert aria-hidden="true" className="mt-0.5 shrink-0" size={16} />
            <div>
              <strong className="block">AI analysis completed with warnings</strong>
              <span>{aiWarnings.join(" ")} Deterministic results and unresolved cases remain available.</span>
            </div>
          </div>
        ) : null}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            detail={`${metricNumber(ai.eligible_cases)} eligible cases`}
            href={`/runs/${runId}/cases?ai=yes`}
            icon={Sparkles}
            label="AI-Assisted Cases"
            tone="ai"
            value={formatInteger(aiAssisted)}
          />
          <MetricCard
            detail="Bounded exception analysis"
            href={`/runs/${runId}/audit`}
            icon={Bot}
            label="AI Calls"
            tone="ai"
            value={formatInteger(metricNumber(ai.calls))}
          />
          <MetricCard
            detail="Recorded provider estimate"
            href={`/runs/${runId}/audit`}
            icon={CircleDollarSign}
            label="Estimated AI Cost"
            tone="ai"
            value={`$${metricNumber(ai.estimated_cost).toFixed(4)}`}
          />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2" aria-label="Run visualizations">
        <div className="panel min-w-0">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Cases by state</h2>
              <p className="panel-copy">Final deterministic and review states</p>
            </div>
            <span className="text-xl font-bold tabular-nums">{formatInteger(totalCases)}</span>
          </div>
          <div className="grid min-h-[280px] items-center gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_150px]">
            <div className="h-[245px] min-w-0">
              <ResponsiveContainer height="100%" width="100%">
                <PieChart>
                  <Pie data={stateData} dataKey="value" innerRadius={62} outerRadius={88} paddingAngle={2}>
                    {stateData.map((item) => (
                      <Cell fill={stateColors[item.name]} key={item.name} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [value, "Cases"]} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-3">
              {stateData.map((item) => (
                <Link
                  className="flex items-center justify-between gap-3 text-[0.72rem]"
                  href={`/runs/${runId}/cases?state=${
                    item.name === "Verified"
                      ? "RECONCILED"
                      : item.name === "Pending"
                        ? "PENDING_WITHIN_SLA"
                        : item.name === "Invalid"
                          ? "INVALID_INPUT"
                          : "ACTIONABLE_EXCEPTION"
                  }`}
                  key={item.name}
                >
                  <span className="flex items-center gap-2 text-[#596660]">
                    <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: stateColors[item.name] }} />
                    {item.name}
                  </span>
                  <strong>{item.value}</strong>
                </Link>
              ))}
            </div>
          </div>
        </div>

        <div className="panel min-w-0">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Exceptions by reason</h2>
              <p className="panel-copy">Most frequent exception codes</p>
            </div>
          </div>
          <div className="h-[280px] p-4">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={exceptionData} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid horizontal={false} stroke="#e2e8f0" />
                <XAxis allowDecimals={false} type="number" />
                <YAxis dataKey="code" tick={{ fontSize: 10 }} type="category" width={128} />
                <Tooltip />
                <Bar dataKey="count" fill="#e11d48" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel min-w-0">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Cash by confidence</h2>
              <p className="panel-copy">Rupee value across confidence buckets</p>
            </div>
            <Link className="text-[0.72rem] font-bold text-[#0c44ac] hover:text-[#09368b]" href={`/runs/${runId}/cash`}>
              Inspect <ArrowRight aria-hidden="true" className="inline" size={13} />
            </Link>
          </div>
          <div className="h-[230px] p-4">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={cashData} layout="vertical" margin={{ left: 8, right: 12 }}>
                <XAxis tickFormatter={(value) => `₹${Math.round(value / 1000)}k`} type="number" />
                <YAxis dataKey="name" hide type="category" />
                <Tooltip formatter={(value) => formatPaise(Number(value) * 100)} />
                <Bar dataKey="confirmed" fill="#059669" stackId="cash" />
                <Bar dataKey="transit" fill="#d97706" stackId="cash" />
                <Bar dataKey="expected" fill="#0284c7" stackId="cash" />
                <Bar dataKey="risk" fill="#e11d48" stackId="cash" />
                <Bar dataKey="unresolved" fill="#64748b" radius={[0, 3, 3, 0]} stackId="cash" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel min-w-0">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">SLA aging</h2>
              <p className="panel-copy">Cases requiring time-based controls</p>
            </div>
          </div>
          <div className="h-[230px] p-4">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={slaData} layout="vertical" margin={{ left: 10, right: 16 }}>
                <CartesianGrid horizontal={false} stroke="#e2e8f0" />
                <XAxis allowDecimals={false} type="number" />
                <YAxis dataKey="label" tick={{ fontSize: 11 }} type="category" width={100} />
                <Tooltip />
                <Bar dataKey="value" fill="#d97706" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <SettlementQACard runId={runId} />

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Run artifacts</h2>
            <p className="panel-copy">Immutable evidence and operational exports</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 p-4">
          <ExportButton href={exportUrl(runId, "reconciliation.csv")} label="Reconciliation CSV" testId="download-reconciliation" />
          <ExportButton href={exportUrl(runId, "exceptions.csv")} label="Exceptions CSV" />
          <ExportButton href={exportUrl(runId, "audit.json")} label="Audit JSON" />
        </div>
      </section>

      <ClaimsLedgerModal
        isOpen={isClaimsModalOpen}
        onClose={() => setIsClaimsModalOpen(false)}
        runId={runId}
      />
    </div>
  );
}
