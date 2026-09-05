"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  Clock3,
  Fingerprint,
  GitCommitHorizontal,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { useParams } from "next/navigation";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorState } from "@/components/ErrorState";
import { ExportButton } from "@/components/ExportButton";
import { MetricCard } from "@/components/MetricCard";
import { exportUrl, getAudit, getEvaluation, getMetrics, getRun, type AuditEvent } from "@/lib/api";
import {
  formatDateTime,
  formatDuration,
  formatInteger,
  formatPaise,
  formatPercent,
  metricNumber,
  shortId,
  titleCase,
} from "@/lib/format";

export default function AuditPage() {
  const { runId } = useParams<{ runId: string }>();
  const runQuery = useQuery({ queryKey: ["run", runId], queryFn: () => getRun(runId) });
  const metricsQuery = useQuery({ queryKey: ["metrics", runId], queryFn: () => getMetrics(runId) });
  const evaluationQuery = useQuery({
    queryKey: ["evaluation", runId],
    queryFn: () => getEvaluation(runId),
  });
  const auditQuery = useQuery({ queryKey: ["audit", runId], queryFn: () => getAudit(runId) });
  const run = runQuery.data;
  const metrics = metricsQuery.data?.metrics ?? {};
  const evaluation = evaluationQuery.data;
  const aggregate = evaluation?.aggregate ?? metrics;
  const scenarios = Object.entries(evaluation?.scenario_breakdown ?? {});
  const hasRelationshipCounts =
    typeof aggregate.relationship_true_positive_count === "number" &&
    typeof aggregate.relationship_predicted_count === "number" &&
    typeof aggregate.relationship_expected_count === "number";
  const relationshipTruePositives = metricNumber(aggregate.relationship_true_positive_count);
  const totalEvaluatedCases = metricNumber(aggregate.total_truth_cases);

  const columns: DataTableColumn<AuditEvent>[] = [
    {
      key: "time",
      label: "Timestamp",
      sortValue: (event) => new Date(event.created_at).getTime(),
      render: (event) => <time className="whitespace-nowrap">{formatDateTime(event.created_at)}</time>,
    },
    {
      key: "event",
      label: "Event",
      sortValue: (event) => event.event_type,
      render: (event) => <strong className="text-[#3b4842]">{titleCase(event.event_type)}</strong>,
    },
    {
      key: "stage",
      label: "Stage",
      sortValue: (event) => event.stage ?? "",
      render: (event) => titleCase(event.stage),
    },
    {
      key: "actor",
      label: "Actor",
      sortValue: (event) => event.actor ?? "",
      render: (event) => (
        <span className="inline-flex items-center gap-1.5 font-semibold">
          {event.actor === "AI_SUGGESTION" ? <Bot aria-hidden="true" size={12} /> : <ShieldCheck aria-hidden="true" size={12} />}
          {titleCase(event.actor)}
        </span>
      ),
    },
    {
      key: "case",
      label: "Case ID",
      sortValue: (event) => event.case_id ?? "",
      render: (event) => (
        <span className="font-mono text-[0.66rem]" title={event.case_id ?? ""}>
          {event.case_id ? shortId(event.case_id, 18) : "Run-level"}
        </span>
      ),
    },
    {
      key: "rule",
      label: "Rule",
      sortValue: (event) => event.rule_id ?? "",
      render: (event) => event.rule_id ?? "—",
    },
    {
      key: "duration",
      label: "Duration",
      sortValue: (event) => event.duration_ms ?? 0,
      render: (event) => (event.duration_ms === null ? "—" : `${event.duration_ms} ms`),
    },
  ];

  if (runQuery.isLoading || metricsQuery.isLoading || evaluationQuery.isLoading || auditQuery.isLoading) {
    return (
      <div className="space-y-5">
        <div className="skeleton h-16 max-w-xl" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 6 }).map((_, index) => (
            <div className="skeleton h-32" key={index} />
          ))}
        </div>
        <div className="skeleton h-80" />
      </div>
    );
  }

  if (!run || runQuery.error || metricsQuery.error || auditQuery.error) {
    return (
      <ErrorState
        message="Run provenance could not be loaded. The immutable event history remains preserved in the service."
        onRetry={() => {
          void Promise.all([
            runQuery.refetch(),
            metricsQuery.refetch(),
            evaluationQuery.refetch(),
            auditQuery.refetch(),
          ]);
        }}
        error={runQuery.error ?? metricsQuery.error ?? auditQuery.error}
        title="Audit view unavailable"
      />
    );
  }

  return (
    <div className="space-y-6" data-testid="audit-view">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="eyebrow mb-0">Audit &amp; evaluation</p>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#ecfdf5] border border-[#a7f3d0] px-2.5 py-1 text-[0.6rem] font-bold text-[#065f46]">
              <CheckCircle2 aria-hidden="true" size={11} /> Immutable record
            </span>
          </div>
          <h1 className="page-title">Run provenance</h1>
          <p className="page-subtitle">Evaluation, execution versions, checksums, and chronological decisions.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ExportButton href={exportUrl(runId, "evaluation.json")} label="Evaluation JSON" />
          <ExportButton href={exportUrl(runId, "evaluation.md")} label="Evaluation MD" />
          <ExportButton href={exportUrl(runId, "audit.json")} label="Audit JSON" />
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Run provenance details">
        <div className="panel relative overflow-hidden p-4">
          <span className="absolute inset-y-0 left-0 w-[3px] bg-[#0c44ac]" />
          <span className="flex items-center gap-2 pl-2 text-[0.66rem] font-bold text-[#64748b]">
            <span className="flex h-7 w-7 items-center justify-center rounded-[6px] bg-[#eff6ff] text-[#0c44ac]">
              <Fingerprint aria-hidden="true" size={14} />
            </span>
            Dataset checksum
          </span>
          <code className="mt-3 block break-all pl-2 text-[0.66rem] leading-5 text-[#0f172a]">
            {run.dataset_checksum ?? "Not available"}
          </code>
        </div>
        <div className="panel relative overflow-hidden p-4">
          <span className="absolute inset-y-0 left-0 w-[3px] bg-[#059669]" />
          <span className="flex items-center gap-2 pl-2 text-[0.66rem] font-bold text-[#64748b]">
            <span className="flex h-7 w-7 items-center justify-center rounded-[6px] bg-[#ecfdf5] text-[#059669]">
              <Scale aria-hidden="true" size={14} />
            </span>
            Policy and rules
          </span>
          <dl className="mt-3 space-y-2 pl-2 text-[0.69rem]">
            <div className="flex justify-between gap-3">
              <dt className="text-[#64748b]">Policy</dt>
              <dd className="m-0 font-semibold text-[#0f172a]">{run.policy_id} {run.policy_version}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-[#64748b]">Rule set</dt>
              <dd className="m-0 font-semibold text-[#0f172a]">{run.rule_set_version ?? "Not available"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-[#64748b]">Application</dt>
              <dd className="m-0 font-semibold text-[#0f172a]">{run.app_version ?? "Not available"}</dd>
            </div>
          </dl>
        </div>
        <div className="panel relative overflow-hidden p-4 sm:col-span-2 xl:col-span-1">
          <span className="absolute inset-y-0 left-0 w-[3px] bg-[#6366f1]" />
          <span className="flex items-center gap-2 pl-2 text-[0.66rem] font-bold text-[#64748b]">
            <span className="flex h-7 w-7 items-center justify-center rounded-[6px] bg-[#eef2ff] text-[#4338ca]">
              <Bot aria-hidden="true" size={14} />
            </span>
            AI provenance
          </span>
          <dl className="mt-3 space-y-2 pl-2 text-[0.69rem]">
            <div className="flex justify-between gap-3">
              <dt className="text-[#64748b]">Model</dt>
              <dd className="m-0 font-semibold text-[#0f172a]">{run.ai_model ?? "Unavailable"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-[#64748b]">Prompt</dt>
              <dd className="m-0 font-semibold text-[#0f172a]">{run.ai_prompt_version ?? "Not available"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-[#64748b]">Run duration</dt>
              <dd className="m-0 font-semibold text-[#0f172a]">{formatDuration((run.duration_ms ?? 0) / 1000)}</dd>
            </div>
          </dl>
        </div>
      </section>

      {evaluationQuery.error ? <ErrorState title="Evaluation unavailable" message={evaluationQuery.error.message} error={evaluationQuery.error} onRetry={() => void evaluationQuery.refetch()} /> : null}
      <section aria-labelledby="evaluation-summary-heading">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="m-0 text-[0.92rem] font-bold" id="evaluation-summary-heading">
              Ground-truth evaluation
            </h2>
            <p className="panel-copy">Dataset {evaluation?.dataset_id ?? "not evaluated"}</p>
          </div>
          {evaluation ? (
            <span className="inline-flex items-center gap-1.5 rounded-[4px] border border-[#a7f3d0] bg-[#ecfdf5] px-2 py-1 text-[0.67rem] font-bold text-[#065f46]">
              <CheckCircle2 aria-hidden="true" size={12} /> Evaluation complete
            </span>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
          <MetricCard
            detail={
              hasRelationshipCounts
                ? `${formatInteger(relationshipTruePositives)} / ${formatInteger(metricNumber(aggregate.relationship_predicted_count))} predicted relationships`
                : "Ground-truth evaluation"
            }
            label="Precision"
            value={evaluation && typeof aggregate.relationship_precision === "number" ? formatPercent(aggregate.relationship_precision) : "Not evaluated"}
            tone="verified"
          />
          <MetricCard
            detail={
              hasRelationshipCounts
                ? `${formatInteger(relationshipTruePositives)} / ${formatInteger(metricNumber(aggregate.relationship_expected_count))} expected relationships`
                : "Ground-truth evaluation"
            }
            label="Recall"
            value={evaluation && typeof aggregate.relationship_recall === "number" ? formatPercent(aggregate.relationship_recall) : "Not evaluated"}
            tone="verified"
          />
          <MetricCard
            detail="Harmonic mean of precision and recall"
            label="F1 Score"
            value={evaluation && typeof aggregate.relationship_f1 === "number" ? formatPercent(aggregate.relationship_f1) : "Not evaluated"}
            tone="verified"
          />
          <MetricCard
            detail={`${formatInteger(metricNumber(aggregate.stp_reconciled_case_count))} / ${formatInteger(totalEvaluatedCases)} auto-reconciled cases`}
            label="STP Rate"
            value={evaluation && typeof aggregate.stp_rate === "number" ? formatPercent(aggregate.stp_rate) : "Not evaluated"}
          />
          <MetricCard
            detail={`${formatPaise(metricNumber(aggregate.reconciled_gross_amount_paise))} / ${formatPaise(metricNumber(aggregate.total_gross_amount_paise))} gross value`}
            label="Monetary Reconciliation"
            value={evaluation && typeof aggregate.monetary_reconciliation_rate === "number" ? formatPercent(aggregate.monetary_reconciliation_rate) : "Not evaluated"}
          />
          <MetricCard
            detail={`${formatPaise(metricNumber(aggregate.false_positive_amount_paise))} across ${formatInteger(totalEvaluatedCases)} evaluated cases`}
            label="False Positives"
            tone={metricNumber(aggregate.false_positive_count) ? "risk" : "verified"}
            value={evaluation && typeof aggregate.false_positive_count === "number" ? formatInteger(aggregate.false_positive_count) : "Not evaluated"}
          />
        </div>
      </section>

      <section className="panel overflow-hidden" aria-labelledby="scenario-breakdown-heading">
        <div className="panel-header">
          <div>
            <h2 className="panel-title" id="scenario-breakdown-heading">
              Scenario breakdown
            </h2>
            <p className="panel-copy">Metrics grouped by the private evaluation scenario label</p>
          </div>
          <GitCommitHorizontal aria-hidden="true" className="text-[#65716c]" size={17} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[850px] border-collapse text-left text-[0.72rem]">
            <thead className="border-b border-[#dbe3df] bg-[#f4f7f5] text-[#5d6c65]">
              <tr>
                <th className="px-4 py-3 font-bold">Scenario</th>
                <th className="px-3 py-3 text-right font-bold">Cases</th>
                <th className="px-3 py-3 text-right font-bold">Precision</th>
                <th className="px-3 py-3 text-right font-bold">Recall</th>
                <th className="px-3 py-3 text-right font-bold">F1</th>
                <th className="px-3 py-3 text-right font-bold">State accuracy</th>
                <th className="px-3 py-3 text-right font-bold">Cash accuracy</th>
                <th className="px-3 py-3 text-right font-bold">False positives</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map(([scenario, values]) => (
                <tr className="border-b border-[#e4e9e6] transition-colors last:border-0 hover:bg-[#f8faf9]" key={scenario}>
                  <td className="px-4 py-3 font-semibold">{titleCase(scenario)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatInteger(metricNumber(values.total_truth_cases))}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatPercent(metricNumber(values.relationship_precision))}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatPercent(metricNumber(values.relationship_recall))}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatPercent(metricNumber(values.relationship_f1))}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatPercent(metricNumber(values.case_state_accuracy))}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatPercent(metricNumber(values.cash_bucket_accuracy))}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatInteger(metricNumber(values.false_positive_count))}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!scenarios.length ? (
            <div className="px-5 py-12 text-center text-[0.76rem] text-[#74807b]">
              Scenario metrics are available after evaluation completes.
            </div>
          ) : null}
        </div>
      </section>

      <section className="panel overflow-hidden" aria-labelledby="event-log-heading">
        <div className="panel-header">
          <div>
            <h2 className="panel-title" id="event-log-heading">
              Immutable event log
            </h2>
            <p className="panel-copy">{formatInteger(auditQuery.data?.total ?? 0)} chronological run and case events</p>
          </div>
          <Clock3 aria-hidden="true" className="text-[#65716c]" size={17} />
        </div>
        <DataTable
          columns={columns}
          filterPlaceholder="Search event, case, actor, stage, or rule"
          filterText={(event) =>
            [event.event_type, event.case_id, event.actor, event.stage, event.rule_id].filter(Boolean).join(" ")
          }
          getRowKey={(event) => event.id}
          pageSize={20}
          rows={auditQuery.data?.items ?? []}
        />
      </section>
    </div>
  );
}
