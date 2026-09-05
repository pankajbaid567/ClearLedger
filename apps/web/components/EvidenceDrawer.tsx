"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  CircleSlash2,
  Database,
  FileKey2,
  GitBranch,
  ListChecks,
  ShieldAlert,
  Sparkles,
  UserRound,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  getAIAnalysis,
  getAudit,
  getCandidates,
  getCase,
  getEvidence,
  getReceipt,
  type ReviewAction,
} from "@/lib/api";
import { formatDateTime, formatPaise, shortId, titleCase } from "@/lib/format";

import { AIBadge } from "./AIBadge";
import { AmountDisplay } from "./AmountDisplay";
import { EquationCard, type EquationLine } from "./EquationCard";
import { EvidenceGraph } from "./EvidenceGraph";
import { ExceptionCard } from "./ExceptionCard";
import { ReviewActionDialog } from "./ReviewActionDialog";
import { StatusBadge } from "./StatusBadge";
import { ErrorState } from "./ErrorState";
import { useIdentity } from "./AccessBoundary";
import { useDialogFocus } from "@/lib/useDialogFocus";

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(value: unknown, fallback = "Not available"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function SourceRecord({ record }: { record: Record<string, unknown> }) {
  const raw = objectValue(record.raw_values);
  const normalized = objectValue(record.normalized_fields);
  const sourceType = stringValue(record.source_type, "source");
  const importantRaw = Object.entries(raw);

  return (
    <article className="min-w-0 overflow-hidden rounded-[8px] border border-[#dbe3df] bg-white shadow-[0_1px_2px_rgba(23,38,32,0.04)]">
      <div className="flex items-center justify-between gap-3 border-b border-[#e1e7e4] bg-[#fbfcfb] px-3.5 py-3">
        <span className="flex min-w-0 items-center gap-2 text-[0.72rem] font-bold">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[5px] bg-[#edf1ef] text-[#5e6c66]">
            <Database aria-hidden="true" size={13} />
          </span>
          <span className="truncate">{titleCase(sourceType)}</span>
        </span>
        <span className="truncate font-mono text-[0.62rem] text-[#7b8681]">
          {shortId(stringValue(record.entity_id, stringValue(record.source_record_id)), 16)}
        </span>
      </div>
      <div className="p-3.5">
        <p className="m-0 text-[0.63rem] font-bold text-[#75817c] uppercase">Raw source</p>
        <dl className="mt-2 space-y-1.5">
          {importantRaw.map(([key, value]) => (
            <div className="grid grid-cols-[minmax(90px,0.8fr)_minmax(0,1.2fr)] gap-2 text-[0.67rem]" key={key}>
              <dt className="truncate text-[#7a8580]" title={key}>
                {titleCase(key)}
              </dt>
              <dd className="m-0 break-all font-medium text-[#3f4a45]">{stringValue(value)}</dd>
            </div>
          ))}
        </dl>
        {Object.keys(normalized).length ? (
          <details className="mt-3 border-t border-[#e4e7e5] pt-2">
            <summary className="cursor-pointer text-[0.66rem] font-bold text-[#17664d]">
              Normalized fields ({Object.keys(normalized).length})
            </summary>
            <div className="mt-2 space-y-2">
              {Object.entries(normalized).map(([key, value]) => {
                const field = objectValue(value);
                return (
                    <div className="rounded-[5px] border border-[#e5eae7] bg-[#f7f9f8] px-2.5 py-2" key={key}>
                    <div className="flex items-center justify-between gap-2 text-[0.65rem]">
                      <strong>{titleCase(key)}</strong>
                      <span className="rounded-[3px] bg-[#e5eee9] px-1.5 py-0.5 text-[0.58rem] font-bold text-[#3f6e5b]">
                        deterministic_normalized
                      </span>
                    </div>
                    <div className="mt-1 grid grid-cols-2 gap-2 text-[0.62rem] text-[#66726d]">
                      <span className="break-all">Raw: {stringValue(field.raw)}</span>
                      <span className="break-all">Value: {stringValue(field.normalized)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </details>
        ) : null}
        <span className="mt-3 inline-flex rounded-[3px] bg-[#eef0ef] px-1.5 py-0.5 text-[0.58rem] font-bold text-[#626c67]">
          raw_source
        </span>
      </div>
    </article>
  );
}

export function EvidenceDrawer({
  caseId,
  runId,
  onClose,
}: {
  caseId: string | null;
  runId: string;
  onClose: () => void;
}) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const identity = useIdentity();
  const drawerRef = useRef<HTMLElement>(null);
  useDialogFocus(drawerRef, Boolean(caseId), onClose);
  const [reviewAction, setReviewAction] = useState<ReviewAction>("approve");
  const [notice, setNotice] = useState<string | null>(null);
  const enabled = Boolean(caseId);
  const caseQuery = useQuery({
    queryKey: ["case", runId, caseId],
    queryFn: () => getCase(runId, caseId as string),
    enabled,
  });
  const evidenceQuery = useQuery({
    queryKey: ["evidence", runId, caseId],
    queryFn: () => getEvidence(runId, caseId as string),
    enabled,
  });
  const receiptQuery = useQuery({
    queryKey: ["receipt", runId, caseId],
    queryFn: () => getReceipt(runId, caseId as string),
    enabled,
  });
  const candidatesQuery = useQuery({
    queryKey: ["candidates", runId, caseId],
    queryFn: () => getCandidates(runId, caseId as string),
    enabled,
  });
  const aiQuery = useQuery({
    queryKey: ["ai-analysis", runId, caseId],
    queryFn: () => getAIAnalysis(runId, caseId as string),
    enabled: Boolean(caseId && caseQuery.data?.ai_assisted),
    retry: false,
  });
  const auditQuery = useQuery({
    queryKey: ["audit", runId],
    queryFn: () => getAudit(runId),
    enabled,
  });

  useEffect(() => { setNotice(null); setReviewOpen(false); }, [caseId]);

  const caseData = caseQuery.data;
  const caseRecords = caseData?.records;
  const records = useMemo(() => caseRecords ?? [], [caseRecords]);
  const equation = useMemo(() => {
    const components = records.filter((record) => record.source_type === "settlement_components");
    const lines: EquationLine[] = components.map((record) => ({
      label: titleCase(stringValue(record.component_type, "Settlement component")),
      amountPaise: Math.abs(numberValue(record.amount_paise)),
      sign: stringValue(record.direction, "CREDIT") === "DEBIT" ? "debit" : "credit",
      id: stringValue(record.entity_id, `${record.source_type}-${components.indexOf(record)}`),
    }));
    const bankEdges = evidenceQuery.data?.edges.filter((edge) => edge.relationship_type === "settlement_bank") ?? [];
    return { lines, bankCreditPaise: bankEdges.length ? bankEdges.reduce((sum, edge) => sum + edge.allocated_amount_paise, 0) : null };
  }, [records, evidenceQuery.data]);

  const auditEvents = (auditQuery.data?.items ?? []).filter((item) => item.case_id === caseId);
  const isLoading =
    caseQuery.isLoading || evidenceQuery.isLoading || receiptQuery.isLoading || candidatesQuery.isLoading;
  const reviewable = Boolean(
    identity?.permissions.includes("review") && caseData &&
      [
        "ACTIONABLE_EXCEPTION",
        "SUGGESTED_FOR_REVIEW",
        "APPROVED_PENDING_VERIFICATION",
        "DEFERRED",
        "REJECTED_SUGGESTION",
      ].includes(caseData.case_state),
  );
  const approvalAlreadyRecorded =
    caseData?.case_state === "APPROVED_PENDING_VERIFICATION";
  const isVerifiedSuggestion = Boolean(
    caseData?.case_state === "SUGGESTED_FOR_REVIEW" && caseData.ai_assisted,
  );
  const canApprove = reviewable && !approvalAlreadyRecorded;
  const failedInvariantCount =
    receiptQuery.data?.invariants.filter((item) => !item.passed).length ?? 0;
  const approvalRequirements = [
    failedInvariantCount
      ? `${failedInvariantCount} failed financial ${failedInvariantCount === 1 ? "check" : "checks"}`
      : null,
    caseData?.residual_paise
      ? `${formatPaise(Math.abs(caseData.residual_paise))} unexplained residual`
      : null,
  ].filter((item): item is string => Boolean(item));
  const approvalBlockReason = approvalAlreadyRecorded
    ? "Approval is already recorded. This case remains pending deterministic verification."
    : undefined;
  const approvalGuidance = isVerifiedSuggestion
    ? "Approval promotes the pre-verified suggestion and reruns every financial invariant. The case reconciles only if the complete evidence graph passes."
    : approvalAlreadyRecorded
      ? "The human approval is recorded, but cash remains unreleased until every financial invariant passes."
      : `This approval will be recorded as Approved Pending Verification${
          approvalRequirements.length ? ` because the case has ${approvalRequirements.join(" and ")}` : ""
        }. It will not reconcile the case or release cash.`;

  function openReview(action: ReviewAction) {
    if (action === "approve" && !canApprove) return;
    setReviewAction(action);
    setReviewOpen(true);
  }

  if (!caseId) return null;

  return (
    <>
      <div
        aria-hidden="true"
        className="fixed inset-0 z-40 bg-[#111915]/45"
        onClick={onClose}
      />
      <aside
        ref={drawerRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence for ${caseId}`}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[880px] flex-col overflow-hidden border-l border-[#cbd5d0] bg-[#f3f6f5] shadow-[-18px_0_48px_rgba(17,33,27,0.16)]"
        data-testid="evidence-drawer"
      >
        <header className="z-10 shrink-0 border-b border-[#dbe3df] bg-white px-4 pt-4 sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="eyebrow">Case evidence</p>
              <h2 className="m-0 truncate font-mono text-[1.05rem] font-bold text-[#1d2a25]">{caseId}</h2>
            </div>
            <button aria-label="Close evidence drawer" className="btn btn-secondary btn-icon" onClick={onClose}>
              <X aria-hidden="true" size={18} />
            </button>
          </div>
          {caseData ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 pb-3">
              <StatusBadge status={caseData.case_state} />
              <span className="rounded-[4px] border border-[#d5dad7] bg-[#f7f8f7] px-2 py-1 text-[0.67rem] font-bold text-[#596560]">
                {titleCase(caseData.decision_level)}
              </span>
              {caseData.ai_assisted ? <AIBadge /> : null}
              {caseData.human_reviewed ? (
                <span className="inline-flex items-center gap-1 rounded-[4px] border border-[#cfd8d3] bg-white px-2 py-1 text-[0.67rem] font-bold text-[#4f6259]">
                  <UserRound aria-hidden="true" size={11} /> Human reviewed
                </span>
              ) : null}
            </div>
          ) : null}
          <nav aria-label="Evidence sections" className="-mx-4 flex overflow-x-auto border-t border-[#e7ece9] px-4 sm:-mx-6 sm:px-6">
            {[
              ["source-records-heading", "Sources"],
              ["evidence-graph-heading", "Graph"],
              ["invariants-heading", "Checks"],
              ["audit-timeline-heading", "Timeline"],
            ].map(([target, label]) => (
              <a
                className="flex min-h-10 shrink-0 items-center border-b-2 border-transparent px-3 text-[0.66rem] font-bold text-[#67756e] hover:border-[#8eadeb] hover:text-[#245fda]"
                href={`#${target}`}
                key={target}
              >
                {label}
              </a>
            ))}
          </nav>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
        {caseQuery.error || evidenceQuery.error || receiptQuery.error || candidatesQuery.error ? <ErrorState title="Case evidence unavailable" message="Some proof could not be loaded. Retry before making a review decision." error={caseQuery.error ?? evidenceQuery.error ?? receiptQuery.error ?? candidatesQuery.error} onRetry={() => { void Promise.all([caseQuery.refetch(), evidenceQuery.refetch(), receiptQuery.refetch(), candidatesQuery.refetch()]); }} /> : isLoading || !caseData ? (
          <div className="space-y-4 p-4 sm:p-6">
            <div className="skeleton h-28" />
            <div className="skeleton h-72" />
            <div className="skeleton h-56" />
          </div>
        ) : (
          <div className="space-y-5 p-4 sm:p-6">
            <section className="grid grid-cols-3 gap-2.5" aria-label="Case amounts">
              <div className="relative overflow-hidden rounded-[7px] border border-[#dbe3df] bg-white px-3 py-3.5 shadow-[0_1px_2px_rgba(23,38,32,0.04)]">
                <span className="absolute inset-y-0 left-0 w-[3px] bg-[#68756f]" />
                <span className="block text-[0.63rem] font-bold text-[#77827d]">Gross</span>
                <AmountDisplay className="mt-2 block text-[0.9rem] font-bold" paise={caseData.gross_amount_paise} />
              </div>
              <div className="relative overflow-hidden rounded-[7px] border border-[#dbe3df] bg-white px-3 py-3.5 shadow-[0_1px_2px_rgba(23,38,32,0.04)]">
                <span className="absolute inset-y-0 left-0 w-[3px] bg-[#245fda]" />
                <span className="block text-[0.63rem] font-bold text-[#77827d]">Explained net</span>
                <AmountDisplay className="mt-2 block text-[0.9rem] font-bold" paise={caseData.net_amount_paise} />
              </div>
              <div className="relative overflow-hidden rounded-[7px] border border-[#dbe3df] bg-white px-3 py-3.5 shadow-[0_1px_2px_rgba(23,38,32,0.04)]">
                <span className={`absolute inset-y-0 left-0 w-[3px] ${caseData.residual_paise ? "bg-[#c43f3a]" : "bg-[#087a55]"}`} />
                <span className="block text-[0.63rem] font-bold text-[#77827d]">Residual</span>
                <AmountDisplay
                  className={`mt-2 block text-[0.9rem] font-bold ${caseData.residual_paise ? "text-[#b53732]" : "text-[#087a55]"}`}
                  paise={caseData.residual_paise}
                />
              </div>
            </section>

            {caseData.exception_code ? <ExceptionCard caseData={caseData} /> : null}
            <details className="rounded border border-slate-200 bg-white p-3 text-xs"><summary className="cursor-pointer font-semibold">Baseline and current review proof</summary><dl className="mt-3 space-y-2 break-all"><div><dt className="font-semibold">Immutable engine baseline checksum</dt><dd className="m-0 font-mono">{receiptQuery.data?.baseline_result_checksum ?? receiptQuery.data?.result_checksum ?? "Unavailable"}</dd></div><div><dt className="font-semibold">Current review checksum</dt><dd className="m-0 font-mono">{receiptQuery.data?.current_review_checksum ?? "Unavailable"}</dd></div></dl>{receiptQuery.data?.review_checksum_payload ? <pre className="mt-3 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2">{JSON.stringify(receiptQuery.data.review_checksum_payload, null, 2)}</pre> : null}</details>

            <section aria-labelledby="source-records-heading">
              <div className="mb-3 flex items-center gap-2">
                <FileKey2 aria-hidden="true" className="text-[#53615b]" size={16} />
                <h3 className="m-0 text-[0.86rem] font-bold" id="source-records-heading">
                  Source records
                </h3>
                <span className="text-[0.68rem] text-[#78837e]">{records.length} records</span>
              </div>
              {records.length ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {records.map((record, index) => (
                    <SourceRecord key={`${stringValue(record.entity_id)}-${index}`} record={record} />
                  ))}
                </div>
              ) : (
                <div className="rounded-[6px] border border-dashed border-[#c9d0cc] bg-white px-5 py-8 text-center text-[0.75rem] text-[#74807b]">
                  No source records are attached to this case.
                </div>
              )}
            </section>

            <section aria-labelledby="evidence-graph-heading">
              <div className="mb-3 flex items-center gap-2">
                <GitBranch aria-hidden="true" className="text-[#53615b]" size={16} />
                <h3 className="m-0 text-[0.86rem] font-bold" id="evidence-graph-heading">
                  Evidence graph
                </h3>
              </div>
              {evidenceQuery.data ? <EvidenceGraph graph={evidenceQuery.data} /> : null}
            </section>

            <EquationCard
              bankCreditPaise={equation.bankCreditPaise}
              bankVerified={Boolean(receiptQuery.data?.all_invariants_passed && caseData.case_state === "RECONCILED")}
              lines={equation.lines}
              netSettlementPaise={caseData.net_amount_paise}
              residualPaise={caseData.residual_paise}
            />

            {auditQuery.error ? <ErrorState title="Audit timeline unavailable" message={auditQuery.error.message} error={auditQuery.error} onRetry={() => void auditQuery.refetch()} /> : null}
            <section className="panel overflow-hidden" aria-labelledby="invariants-heading">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title" id="invariants-heading">
                    Invariant results
                  </h3>
                  <p className="panel-copy">Deterministic checks required for verification</p>
                </div>
                {receiptQuery.data?.all_invariants_passed ? (
                  <CheckCircle2 aria-label="All passed" className="text-[#16734f]" size={18} />
                ) : (
                  <ShieldAlert aria-label="Checks failed" className="text-[#c63e39]" size={18} />
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[600px] border-collapse text-left text-[0.68rem]">
                  <thead className="bg-[#f7f8f6] text-[#68746f]">
                    <tr>
                      <th className="px-3 py-2 font-bold">Result</th>
                      <th className="px-3 py-2 font-bold">Invariant</th>
                      <th className="px-3 py-2 font-bold">Expected</th>
                      <th className="px-3 py-2 font-bold">Actual</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(receiptQuery.data?.invariants ?? []).map((item) => (
                      <tr className="border-t border-[#e4e7e5]" key={item.invariant_id}>
                        <td className="px-3 py-2.5">
                          {item.passed ? (
                            <span className="inline-flex items-center gap-1 font-bold text-[#16734f]">
                              <CheckCircle2 aria-hidden="true" size={13} /> Pass
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 font-bold text-[#b73530]">
                              <XCircle aria-hidden="true" size={13} /> Fail
                            </span>
                          )}
                        </td>
                        <td className="max-w-[240px] px-3 py-2.5">
                          <strong className="block text-[#37433e]">{item.invariant_id}</strong>
                          <span className="mt-0.5 block text-[#76817c]">{item.message ?? "No detail"}</span>
                        </td>
                        <td className="px-3 py-2.5 font-mono">{stringValue(item.expected_value)}</td>
                        <td className="px-3 py-2.5 font-mono">{stringValue(item.actual_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel overflow-hidden" aria-labelledby="candidates-heading">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title" id="candidates-heading">
                    Candidate matches
                  </h3>
                  <p className="panel-copy">Accepted, ambiguous, and rejected relationships considered</p>
                </div>
                <span className="text-sm font-bold">{candidatesQuery.data?.items.length ?? 0}</span>
              </div>
              <div className="divide-y divide-[#e3e6e4]">
                {(candidatesQuery.data?.items ?? []).map((candidate, index) => (
                  <div className="px-4 py-3" key={`${candidate.source_entity_id}-${candidate.target_entity_id}-${index}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[0.7rem] font-bold text-[#3f4b46]">
                        {titleCase(candidate.relationship_type)}
                      </span>
                      <span
                        className={`rounded-[3px] px-1.5 py-0.5 text-[0.6rem] font-bold ${
                          candidate.rejection_reason
                            ? "bg-[#fdeceb] text-[#a93430]"
                            : "bg-[#e7f5ee] text-[#126344]"
                        }`}
                      >
                        {candidate.rejection_reason ? "Rejected" : titleCase(candidate.decision_level)}
                      </span>
                    </div>
                    <div className="mt-2 flex min-w-0 items-center gap-2 font-mono text-[0.62rem] text-[#6d7974]">
                      <span className="truncate">{shortId(candidate.source_entity_id, 17)}</span>
                      <ArrowRight aria-hidden="true" className="shrink-0" size={12} />
                      <span className="truncate">{shortId(candidate.target_entity_id, 17)}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[0.62rem] text-[#6b7772]">
                      <AmountDisplay paise={candidate.allocated_amount_paise} />
                      <span>{candidate.rule_id ?? "No rule"}</span>
                      <span>{titleCase(candidate.actor_type)}</span>
                      {candidate.match_score !== null ? <span>Score {candidate.match_score.toFixed(2)}</span> : null}
                    </div>
                    {candidate.rejection_reason ? (
                      <p className="mb-0 mt-2 rounded-[4px] bg-[#fff3f2] px-2.5 py-2 text-[0.64rem] text-[#8d3b37]">
                        {titleCase(candidate.rejection_reason)}
                      </p>
                    ) : null}
                  </div>
                ))}
                {!candidatesQuery.data?.items.length ? (
                  <p className="m-0 px-4 py-8 text-center text-[0.74rem] text-[#74807b]">
                    No candidate relationships were generated.
                  </p>
                ) : null}
              </div>
            </section>

            {caseData.ai_assisted || aiQuery.data ? (
              <section className="rounded-[6px] border border-[#cbaee4] bg-[#fbf8fe]" aria-labelledby="ai-analysis-heading">
                <div className="flex items-start justify-between gap-3 border-b border-[#e0d1ed] px-4 py-3">
                  <div>
                    <h3 className="m-0 flex items-center gap-2 text-[0.84rem] font-bold text-[#59337d]" id="ai-analysis-heading">
                      <Sparkles aria-hidden="true" size={15} /> AI exception analysis
                    </h3>
                    <p className="mb-0 mt-1 text-[0.67rem] font-semibold text-[#815da0]">
                      This analysis is non-authoritative.
                    </p>
                  </div>
                  <AIBadge />
                </div>
                <div className="space-y-3 p-4 text-[0.72rem]">
                  {aiQuery.data?.ai_response ? (
                    <>
                      <div>
                        <span className="block text-[0.63rem] font-bold text-[#8665a0]">Hypothesis</span>
                        <strong className="mt-1 block text-[#4e3167]">
                          {titleCase(stringValue(aiQuery.data.ai_response.hypothesis_code))}
                        </strong>
                      </div>
                      <div>
                        <span className="block text-[0.63rem] font-bold text-[#8665a0]">Explanation</span>
                        <p className="mb-0 mt-1 leading-5 text-[#5d4b68]">
                          {stringValue(aiQuery.data.ai_response.explanation)}
                        </p>
                      </div>
                      <div>
                        <span className="block text-[0.63rem] font-bold text-[#8665a0]">Recommended action</span>
                        <p className="mb-0 mt-1 font-semibold text-[#4e3167]">
                          {titleCase(stringValue(aiQuery.data.ai_response.recommended_action_code))}
                        </p>
                      </div>
                    </>
                  ) : (
                    <p className="m-0 text-[#715d7d]">The analysis packet was recorded without an authoritative suggestion.</p>
                  )}
                  {aiQuery.data ? (
                    <details className="border-t border-[#e2d5ec] pt-3">
                      <summary className="cursor-pointer font-bold text-[#6f4790]">Evidence packet sent</summary>
                      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-[4px] bg-white p-3 text-[0.61rem] leading-4 text-[#554b5b]">
                        {JSON.stringify(aiQuery.data.evidence_packet, null, 2)}
                      </pre>
                    </details>
                  ) : null}
                </div>
              </section>
            ) : null}

            <section className="panel overflow-hidden" aria-labelledby="audit-timeline-heading">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title" id="audit-timeline-heading">
                    Audit timeline
                  </h3>
                  <p className="panel-copy">Chronological events linked to this case</p>
                </div>
                <ListChecks aria-hidden="true" className="text-[#65716c]" size={17} />
              </div>
              <ol className="m-0 list-none divide-y divide-[#e4e7e5] p-0">
                {auditEvents.map((event) => (
                  <li className="grid grid-cols-[22px_minmax(0,1fr)] gap-2 px-4 py-3" key={event.id}>
                    <span className="mt-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#e8efeb] text-[#47705f]">
                      {event.actor === "AI_SUGGESTION" ? (
                        <Bot aria-hidden="true" size={11} />
                      ) : event.actor === "HUMAN" ? (
                        <UserRound aria-hidden="true" size={11} />
                      ) : (
                        <ChevronRight aria-hidden="true" size={11} />
                      )}
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <strong className="text-[0.7rem]">{titleCase(event.event_type)}</strong>
                        <time className="text-[0.61rem] text-[#7a8580]">{formatDateTime(event.created_at)}</time>
                      </div>
                      <p className="mb-0 mt-1 text-[0.63rem] text-[#6d7974]">
                        {titleCase(event.actor)} · {titleCase(event.stage)}
                        {event.rule_id ? ` · ${event.rule_id}` : ""}
                      </p>
                    </div>
                  </li>
                ))}
                {!auditEvents.length ? (
                  <li className="px-4 py-8 text-center text-[0.72rem] text-[#74807b]">
                    No case-specific audit events were recorded.
                  </li>
                ) : null}
              </ol>
            </section>
          </div>
        )}
        </div>

        {reviewable ? (
          <section
            aria-labelledby="review-controls-heading"
            className="z-10 shrink-0 border-t border-[#cfd8d3] bg-white px-4 py-3 shadow-[0_-8px_24px_rgba(23,38,32,0.08)] sm:px-6"
          >
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="m-0 text-[0.76rem] font-bold text-[#27352f]" id="review-controls-heading">
                  Human decision
                </h3>
                <p className="mb-0 mt-0.5 text-[0.62rem] text-[#718079]">Recorded as {identity?.subject ?? "authenticated operator"}</p>
              </div>
              {notice ? (
                <span className="inline-flex items-center gap-1.5 text-[0.66rem] font-bold text-[#08724f]" role="status">
                  <CheckCircle2 aria-hidden="true" size={13} /> {notice}
                </span>
              ) : null}
            </div>
            {!isVerifiedSuggestion ? (
              <div
                className="mb-3 flex items-start gap-2 rounded-[6px] border border-[#e4c783] bg-[#fff9eb] px-3 py-2 text-[#76520d]"
                data-testid="approval-guidance"
                id="approval-lock-reason"
                role="status"
              >
                <ShieldAlert aria-hidden="true" className="mt-0.5 shrink-0" size={14} />
                <div className="text-[0.66rem] leading-5">
                  <strong className="block">
                    {approvalAlreadyRecorded ? "Approval recorded" : "Approval remains controlled"}
                  </strong>
                  <span>{approvalGuidance}</span>
                </div>
              </div>
            ) : null}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <button
                aria-describedby={!canApprove ? "approval-lock-reason" : undefined}
                className={canApprove ? "btn btn-primary" : "btn btn-secondary"}
                data-testid="approve-case"
                disabled={!canApprove}
                onClick={() => openReview("approve")}
                title={approvalBlockReason}
              >
                <CheckCircle2 aria-hidden="true" size={14} /> Approve
              </button>
              <button className="btn btn-secondary" data-testid="reject-case" onClick={() => openReview("reject")}>
                <CircleSlash2 aria-hidden="true" size={14} /> Reject
              </button>
              <button className="btn btn-secondary" onClick={() => openReview("defer")}>
                <CalendarClock aria-hidden="true" size={14} /> Defer
              </button>
              <button className="btn btn-secondary" onClick={() => openReview("assign")}>
                <UserRound aria-hidden="true" size={14} /> Assign
              </button>
            </div>
          </section>
        ) : null}
      </aside>

      <ReviewActionDialog
        caseId={caseId}
        initialAction={reviewAction}
        approvalBlockReason={approvalBlockReason}
        approvalGuidance={approvalGuidance}
        canApprove={canApprove}
        onClose={() => setReviewOpen(false)}
        onComplete={setNotice}
        open={reviewOpen}
        runId={runId}
      />
    </>
  );
}
