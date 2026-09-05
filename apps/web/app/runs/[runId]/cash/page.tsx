"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Banknote,
  Calculator,
  Minus,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";

import { AmountDisplay } from "@/components/AmountDisplay";
import { CashBucketCard } from "@/components/CashBucketCard";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorState } from "@/components/ErrorState";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ForwardCashForecast } from "@/components/ForwardCashForecast";
import { StatusBadge } from "@/components/StatusBadge";
import { TaxAuditCard } from "@/components/TaxAuditCard";
import {
  getCases,
  getCashForecast,
  getCashPosition,
  getTaxAudit,
  type CaseSummary,
} from "@/lib/api";
import { formatInteger, shortId, titleCase } from "@/lib/format";

const buckets = [
  {
    key: "BANK_CONFIRMED",
    label: "Bank Confirmed",
    description: "Verified credits in bank",
    amountKey: "bank_confirmed_paise",
  },
  {
    key: "SETTLEMENT_CONFIRMED_IN_TRANSIT",
    label: "Settlement In Transit",
    description: "Processed, within bank SLA",
    amountKey: "settlement_confirmed_in_transit_paise",
  },
  {
    key: "EXPECTED_SETTLEMENT",
    label: "Expected Settlement",
    description: "Captured, not yet settled",
    amountKey: "expected_settlement_paise",
  },
  {
    key: "AT_RISK",
    label: "At Risk",
    description: "Overdue or inconsistent",
    amountKey: "at_risk_paise",
  },
  {
    key: "UNRESOLVED",
    label: "Unresolved",
    description: "Cannot safely classify",
    amountKey: "unresolved_paise",
  },
] as const;

export default function CashPositionPage() {
  const { runId } = useParams<{ runId: string }>();
  const searchParams = useSearchParams();
  const requestedBucket = searchParams.get("bucket");
  const selectedBucket = buckets.some((item) => item.key === requestedBucket)
    ? (requestedBucket as (typeof buckets)[number]["key"])
    : "BANK_CONFIRMED";

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [selectedForecastDay, setSelectedForecastDay] = useState<number | null>(null);

  const cashQuery = useQuery({
    queryKey: ["cash", runId],
    queryFn: () => getCashPosition(runId),
  });
  const casesQuery = useQuery({
    queryKey: ["cases", runId],
    queryFn: () => getCases(runId),
  });
  const forecastQuery = useQuery({
    queryKey: ["cash-forecast", runId],
    queryFn: () => getCashForecast(runId),
  });
  const taxAuditQuery = useQuery({
    queryKey: ["tax-audit", runId],
    queryFn: () => getTaxAudit(runId),
  });

  const cash = cashQuery.data;
  const cases = casesQuery.data?.items ?? [];
  const forecast = forecastQuery.data;
  const taxAudit = taxAuditQuery.data;

  const bucketSnapshot = cash?.buckets[selectedBucket];
  const caseIds = new Set(bucketSnapshot?.case_ids ?? []);
  const contributingCases = cases.filter((item) => caseIds.has(item.case_id));

  // Determine active forecast day cases if filtered by forecast day
  const activeForecastDay =
    selectedForecastDay !== null
      ? forecast?.days.find((d) => d.day_offset === selectedForecastDay)
      : null;
  const forecastCaseIds = new Set(activeForecastDay?.case_ids ?? []);

  const displayedCases = activeForecastDay
    ? cases.filter((item) => forecastCaseIds.has(item.case_id))
    : contributingCases;

  const nearTermControlled =
    (cash?.bank_confirmed_paise ?? 0) + (cash?.settlement_confirmed_in_transit_paise ?? 0);
  const totalDeductions =
    (cash?.scheduled_refunds_paise ?? 0) +
    (cash?.known_disputes_paise ?? 0) +
    (cash?.known_reserve_holds_paise ?? 0);
  const openExposure = (cash?.at_risk_paise ?? 0) + (cash?.unresolved_paise ?? 0);

  const columns: DataTableColumn<CaseSummary>[] = [
    {
      key: "case",
      compact: true,
      label: "Case ID",
      sortValue: (item) => item.case_id,
      render: (item) => (
        <span className="font-mono font-semibold" title={item.case_id}>
          {shortId(item.case_id, 18)}
        </span>
      ),
    },
    {
      key: "state",
      compact: true,
      label: "State",
      sortValue: (item) => item.case_state,
      render: (item) => <StatusBadge compact status={item.case_state} />,
    },
    {
      key: "gross",
      label: "Gross Amount",
      sortValue: (item) => item.gross_amount_paise,
      render: (item) => <AmountDisplay paise={item.gross_amount_paise} />,
    },
    {
      key: "net",
      label: "Bucket contribution",
      compact: true,
      sortValue: (item) => item.cash_bucket_contribution_paise ?? 0,
      render: (item) => item.cash_bucket_contribution_paise === undefined ? "Unavailable" : <span><AmountDisplay className="font-bold" paise={item.cash_bucket_contribution_paise} /><span className="block text-xs text-slate-500">{item.cash_contribution_basis ? titleCase(item.cash_contribution_basis) : ""}</span></span>,
    },
    {
      key: "settlement",
      label: "Settlement",
      sortValue: (item) => item.settlement_id ?? "",
      render: (item) => item.settlement_id ?? "Not assigned",
    },
    {
      key: "exception",
      label: "Exception",
      sortValue: (item) => item.exception_code ?? "",
      render: (item) => (
        <span className={item.exception_code ? "font-semibold text-[#a73732]" : "text-[#7b8681]"}>
          {item.exception_code ? titleCase(item.exception_code) : "None"}
        </span>
      ),
    },
  ];

  if (cashQuery.isLoading || casesQuery.isLoading) {
    return (
      <div className="space-y-5">
        <div className="skeleton h-16 max-w-xl" />
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div className="skeleton h-36" key={index} />
          ))}
        </div>
        <div className="skeleton h-72" />
        <div className="skeleton h-56" />
        <div className="skeleton h-80" />
      </div>
    );
  }

  if (!cash || cashQuery.error || casesQuery.error) {
    return (
      <ErrorState
        message="A confidence-based cash snapshot is available after reconciliation completes. No existing cash classification was changed."
        onRetry={() => {
          void Promise.all([
            cashQuery.refetch(),
            casesQuery.refetch(),
            forecastQuery.refetch(),
            taxAuditQuery.refetch(),
          ]);
        }}
        error={cashQuery.error ?? casesQuery.error}
        title="Cash position unavailable"
      />
    );
  }

  return (
    <div className="space-y-6" data-testid="cash-position">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="eyebrow mb-0">Cash position</p>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#eff6ff] border border-[#bfdbfe] px-2.5 py-1 text-[0.6rem] font-bold text-[#0c44ac]">
              <span className="status-dot bg-[#0c44ac]" /> Recorded run snapshot
            </span>
          </div>
          <h1 className="page-title">Confidence-based cash control</h1>
          <p className="text-xs text-slate-500">Source as of {cash.as_of_at ?? "unavailable"} · Execution {cash.execution_revision ?? "—"} / review {cash.review_revision ?? "—"}</p>
          <p className="page-subtitle">
            Net batch receipts and settlement exposures, separated by source evidence. This is not the complete bank balance or spendable balance.
          </p>
        </div>
        <Link className="btn btn-secondary" href={`/runs/${runId}/cases`}>
          View all cases <ArrowRight aria-hidden="true" size={14} />
        </Link>
      </section>

      {/* Top 3 KPI Cards */}
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Link
          className="relative overflow-hidden rounded-[8px] border border-[#a7f3d0] bg-[#ecfdf5] p-5 shadow-xs transition-[border-color,box-shadow,transform] hover:-translate-y-px hover:border-[#059669]/60 hover:shadow-md"
          href={`/runs/${runId}/cases?bucket=BANK_CONFIRMED`}
        >
          <span className="absolute inset-y-0 left-0 w-1.5 bg-[#059669]" />
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-[0.72rem] font-bold text-[#065f46]">
              <ShieldCheck aria-hidden="true" size={16} /> Confirmed batch receipts
            </span>
            <ArrowRight aria-hidden="true" className="text-[#059669]" size={16} />
          </div>
          <AmountDisplay
            className="mt-5 block text-[1.75rem] font-[780] text-[#059669]"
            paise={cash.bank_confirmed_paise}
          />
          <p className="mb-0 mt-2 text-[0.72rem] font-semibold text-[#047857]">
            Verified net settlement receipts in this batch
          </p>
        </Link>

        <Link
          className="relative overflow-hidden rounded-[8px] border border-[#fde68a] bg-[#fffbeb] p-5 shadow-xs transition-[border-color,box-shadow,transform] hover:-translate-y-px hover:border-[#d97706]/60 hover:shadow-md"
          href={`/runs/${runId}/cases?bucket=BANK_CONFIRMED,SETTLEMENT_CONFIRMED_IN_TRANSIT`}
        >
          <span className="absolute inset-y-0 left-0 w-1.5 bg-[#d97706]" />
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-[0.72rem] font-bold text-[#92400e]">
              <Calculator aria-hidden="true" size={16} /> Near-Term Controlled
            </span>
            <ArrowRight aria-hidden="true" className="text-[#d97706]" size={16} />
          </div>
          <AmountDisplay
            className="mt-5 block text-[1.75rem] font-[780] text-[#b45309]"
            paise={nearTermControlled}
          />
          <p className="mb-0 mt-2 text-[0.72rem] font-semibold text-[#78350f]">
            Bank Confirmed + Settlement In Transit
          </p>
        </Link>

        <Link
          className="relative overflow-hidden rounded-[8px] border border-[#fecdd3] bg-[#fff1f2] p-5 shadow-xs transition-[border-color,box-shadow,transform] hover:-translate-y-px hover:border-[#e11d48]/60 hover:shadow-md md:col-span-2 xl:col-span-1"
          href={`/runs/${runId}/cases?bucket=AT_RISK,UNRESOLVED`}
        >
          <span className="absolute inset-y-0 left-0 w-1.5 bg-[#e11d48]" />
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-[0.72rem] font-bold text-[#9f1239]">
              <TriangleAlert aria-hidden="true" size={16} /> Open Exposure
            </span>
            <ArrowRight aria-hidden="true" className="text-[#e11d48]" size={16} />
          </div>
          <AmountDisplay
            className="mt-5 block text-[1.75rem] font-[780] text-[#be123c]"
            paise={openExposure}
          />
          <p className="mb-0 mt-2 text-[0.72rem] font-semibold text-[#881337]">
            At Risk + Unresolved
          </p>
        </Link>
      </section>

      {/* Forward Cash Forecast (T+0 to T+7) */}
      {forecast ? (
        <ForwardCashForecast
          forecast={forecast}
          onSelectDay={(day) => setSelectedForecastDay(day)}
          selectedDay={selectedForecastDay}
        />
      ) : forecastQuery.isLoading ? (
        <div className="skeleton h-72 w-full rounded-[8px]" />
      ) : forecastQuery.error ? <ErrorState title="Forecast unavailable" message={forecastQuery.error.message} error={forecastQuery.error} onRetry={() => void forecastQuery.refetch()} /> : null}

      {/* Recorded fee and tax policy consistency summary */}
      {taxAudit ? (
        <TaxAuditCard runId={runId} taxAudit={taxAudit} />
      ) : taxAuditQuery.isLoading ? (
        <div className="skeleton h-56 w-full rounded-[8px]" />
      ) : taxAuditQuery.error ? <ErrorState title="Policy checks unavailable" message={taxAuditQuery.error.message} error={taxAuditQuery.error} onRetry={() => void taxAuditQuery.refetch()} /> : null}

      {/* Cash Confidence Buckets */}
      <section aria-labelledby="bucket-heading">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="m-0 text-[0.92rem] font-bold" id="bucket-heading">
              Cash confidence buckets
            </h2>
            <p className="panel-copy">Select a bucket to inspect contributing cases</p>
          </div>
          <span className="inline-flex items-center gap-1.5 text-[0.68rem] font-semibold text-[#66736d]">
            <RefreshCw aria-hidden="true" size={12} /> {cashQuery.isFetching || forecastQuery.isFetching ? "Refreshing derived records…" : `Snapshot retrieved ${new Date(cashQuery.dataUpdatedAt).toLocaleTimeString()}`}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {buckets.map((bucketConfig) => {
            const snapshot = cash.buckets[bucketConfig.key];
            return (
              <CashBucketCard
                amountPaise={cash[bucketConfig.amountKey]}
                bucket={bucketConfig.key}
                caseCount={snapshot?.case_ids.length ?? 0}
                description={bucketConfig.description}
                href={`/runs/${runId}/cash?bucket=${bucketConfig.key}`}
                onClick={() => setSelectedForecastDay(null)}
                key={bucketConfig.key}
                label={bucketConfig.label}
                selected={selectedBucket === bucketConfig.key && selectedForecastDay === null}
              />
            );
          })}
        </div>
      </section>

      {/* Contributing Cases & Exposure Deductions */}
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="panel min-w-0 overflow-hidden">
          <div className="panel-header flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="panel-title">
                  {activeForecastDay
                    ? `${activeForecastDay.label} (${activeForecastDay.date}) Inflow Contributors`
                    : `${titleCase(selectedBucket)} contributors`}
                </h2>
                {activeForecastDay ? (
                  <button
                    className="inline-flex items-center gap-1 rounded-full bg-[#edf1ef] px-2 py-0.5 text-[0.62rem] font-bold text-[#55645e] hover:bg-[#e1e6e3]"
                    onClick={() => setSelectedForecastDay(null)}
                    type="button"
                  >
                    Clear forecast filter <X size={10} />
                  </button>
                ) : null}
              </div>
              <p className="panel-copy">
                {activeForecastDay ? (
                  <>
                    {formatInteger(displayedCases.length)} cases arriving ·{" "}
                    <AmountDisplay paise={activeForecastDay.expected_inflow_paise} />
                  </>
                ) : (
                  <>
                    {formatInteger(contributingCases.length)} cases ·{" "}
                    <AmountDisplay paise={bucketSnapshot?.amount_paise ?? 0} />
                  </>
                )}
              </p>
            </div>
            <Banknote aria-hidden="true" className="text-[#65716c]" size={17} />
          </div>
          <DataTable
            columns={columns}
            filterPlaceholder="Search contributing cases"
            filterText={(item) =>
              [item.case_id, item.settlement_id, item.exception_code].filter(Boolean).join(" ")
            }
            getRowKey={(item) => item.case_id}
            onRowClick={(item) => setSelectedCaseId(item.case_id)}
            pageSize={10}
            rows={displayedCases}
          />
        </div>

        <aside className="panel self-start">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Recorded deductions</h2>
              <p className="panel-copy">Components already reflected in settlement net</p>
            </div>
            <TriangleAlert aria-hidden="true" className="text-[#e11d48]" size={17} />
          </div>
          <dl className="m-0 divide-y divide-[#e2e8f0] px-4">
            {[
              ["Scheduled refunds", cash.scheduled_refunds_paise],
              ["Known disputes", cash.known_disputes_paise],
              ["Reserve holds", cash.known_reserve_holds_paise],
            ].map(([label, amount]) => (
              <div
                className="flex items-center justify-between gap-3 py-3 text-[0.73rem]"
                key={String(label)}
              >
                <dt className="flex items-center gap-1.5 text-[#64748b]">
                  <Minus aria-hidden="true" size={12} /> {label}
                </dt>
                <dd className="m-0 font-bold text-[#e11d48]">
                  <AmountDisplay paise={Number(amount)} />
                </dd>
              </div>
            ))}
          </dl>
          <div className="border-t border-[#e2e8f0] bg-[#f8fafc] px-4 py-4">
            <div className="flex items-center justify-between gap-3 text-[0.75rem] font-bold text-[#0f172a]">
              <span>Total recorded deduction components</span>
              <AmountDisplay className="text-[#e11d48]" paise={totalDeductions} />
            </div>
          </div>
        </aside>
      </section>

      <EvidenceDrawer
        caseId={selectedCaseId}
        onClose={() => setSelectedCaseId(null)}
        runId={runId}
      />
    </div>
  );
}
