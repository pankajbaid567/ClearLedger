"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Filter,
  ListFilter,
  RotateCcw,
  Search,
  SlidersHorizontal,
  UserRound,
  X,
} from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { AIBadge } from "@/components/AIBadge";
import { AmountDisplay } from "@/components/AmountDisplay";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { StatusBadge } from "@/components/StatusBadge";
import { getCases, type CaseSummary } from "@/lib/api";
import { ageDays, formatInteger, shortId, titleCase } from "@/lib/format";

const stateOptions = [
  "RECONCILED",
  "PENDING_WITHIN_SLA",
  "ACTIONABLE_EXCEPTION",
  "SUGGESTED_FOR_REVIEW",
  "APPROVED_PENDING_VERIFICATION",
  "INVALID_INPUT",
  "DEFERRED",
  "REJECTED_SUGGESTION",
];
const severityOptions = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const severityRank: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

function FilterMenu({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <details className="relative">
      <summary className="btn btn-secondary list-none">
        <ListFilter aria-hidden="true" size={14} />
        {label}
        {selected.length ? (
          <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-[#0c44ac] px-1 text-[0.61rem] text-white">
            {selected.length}
          </span>
        ) : null}
      </summary>
      <div className="absolute left-0 top-[44px] z-20 min-w-[240px] rounded-[6px] border border-[#e2e8f0] bg-white p-2 shadow-xl">
        {options.map((option) => (
          <label
            className="flex cursor-pointer items-center gap-2 rounded-[4px] px-2 py-2 text-[0.72rem] font-medium hover:bg-[#f8fafc]"
            key={option}
          >
            <span
              className={`flex h-4 w-4 items-center justify-center rounded-[3px] border ${
                selected.includes(option)
                  ? "border-[#0c44ac] bg-[#0c44ac] text-white"
                  : "border-[#cbd5e1] bg-white"
              }`}
            >
              {selected.includes(option) ? <Check aria-hidden="true" size={11} /> : null}
            </span>
            <input
              checked={selected.includes(option)}
              className="sr-only"
              onChange={() => onToggle(option)}
              type="checkbox"
            />
            {titleCase(option)}
          </label>
        ))}
      </div>
    </details>
  );
}

export default function CasesPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialStates = searchParams
    .getAll("state")
    .filter((state) => stateOptions.includes(state));
  const initialBucket = searchParams.get("bucket") ?? "";
  const initialAI = searchParams.get("ai") ?? "all";
  const initialHuman = searchParams.get("human") ?? "all";
  const [states, setStates] = useState<string[]>(initialStates);
  const [severities, setSeverities] = useState<string[]>([]);
  const [codes, setCodes] = useState<string[]>([]);
  const [owner, setOwner] = useState("");
  const [minAge, setMinAge] = useState("");
  const [maxAge, setMaxAge] = useState("");
  const [minAmount, setMinAmount] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [aiFilter, setAiFilter] = useState(initialAI);
  const [humanFilter, setHumanFilter] = useState(initialHuman);
  const [bucket, setBucket] = useState(initialBucket);
  const [sort, setSort] = useState("risk_desc");
  const [advancedOpen, setAdvancedOpen] = useState(
    Boolean(initialBucket || initialAI !== "all" || initialHuman !== "all"),
  );
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  const casesQuery = useQuery({ queryKey: ["cases", runId], queryFn: () => getCases(runId) });
  const caseItems = casesQuery.data?.items;
  const cases = useMemo(() => caseItems ?? [], [caseItems]);
  const exceptionCodes = useMemo(
    () => [...new Set(cases.map((item) => item.exception_code).filter((item): item is string => Boolean(item)))].sort(),
    [cases],
  );
  const cashBuckets = useMemo(
    () => [...new Set(cases.map((item) => item.cash_bucket).filter((item): item is string => Boolean(item)))].sort(),
    [cases],
  );

  const scopedCases = useMemo(
    () =>
      cases.filter((item) => {
      const age = ageDays(item.created_at);
      const riskRupees = item.amount_at_risk_paise / 100;
      return (
        (!severities.length || (item.exception_severity && severities.includes(item.exception_severity))) &&
        (!codes.length || (item.exception_code && codes.includes(item.exception_code))) &&
        (!owner || (item.owner_role ?? "").toLowerCase().includes(owner.toLowerCase())) &&
        (!minAge || age >= Number(minAge)) &&
        (!maxAge || age <= Number(maxAge)) &&
        (!minAmount || riskRupees >= Number(minAmount)) &&
        (!maxAmount || riskRupees <= Number(maxAmount)) &&
        (aiFilter === "all" || item.ai_assisted === (aiFilter === "yes")) &&
        (humanFilter === "all" || item.human_reviewed === (humanFilter === "reviewed")) &&
        (!bucket || item.cash_bucket === bucket)
      );
      }),
    [aiFilter, bucket, cases, codes, humanFilter, maxAge, maxAmount, minAge, minAmount, owner, severities],
  );

  const filteredCases = useMemo(() => {
    const filtered = states.length
      ? scopedCases.filter((item) => states.includes(item.case_state))
      : [...scopedCases];
    return filtered.sort((left, right) => {
      if (sort === "risk_desc") return right.amount_at_risk_paise - left.amount_at_risk_paise;
      if (sort === "age_desc") return ageDays(right.created_at) - ageDays(left.created_at);
      if (sort === "severity") {
        return (severityRank[right.exception_severity ?? ""] ?? 0) - (severityRank[left.exception_severity ?? ""] ?? 0);
      }
      return left.case_id.localeCompare(right.case_id);
    });
  }, [scopedCases, sort, states]);

  function updateUrlFilters(updates: Record<string, string | string[] | null>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(updates).forEach(([key, value]) => {
      params.delete(key);
      if (Array.isArray(value)) value.forEach((item) => params.append(key, item));
      else if (value) params.set(key, value);
    });
    const query = params.toString();
    router.replace(`/runs/${runId}/cases${query ? `?${query}` : ""}`, { scroll: false });
  }

  function applyStates(values: string[]) {
    setStates(values);
    updateUrlFilters({ state: values });
  }

  function applyBucket(value: string) {
    setBucket(value);
    updateUrlFilters({ bucket: value || null });
  }

  function applyAI(value: string) {
    setAiFilter(value);
    updateUrlFilters({ ai: value === "all" ? null : value });
  }

  function applyHuman(value: string) {
    setHumanFilter(value);
    updateUrlFilters({ human: value === "all" ? null : value });
  }

  function toggle(list: string[], value: string, setter: (values: string[]) => void) {
    setter(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  function resetFilters() {
    setStates([]);
    setSeverities([]);
    setCodes([]);
    setOwner("");
    setMinAge("");
    setMaxAge("");
    setMinAmount("");
    setMaxAmount("");
    setAiFilter("all");
    setHumanFilter("all");
    setBucket("");
    updateUrlFilters({ state: null, bucket: null, ai: null, human: null });
  }

  const attentionStates = [
    "ACTIONABLE_EXCEPTION",
    "SUGGESTED_FOR_REVIEW",
    "APPROVED_PENDING_VERIFICATION",
    "DEFERRED",
    "REJECTED_SUGGESTION",
  ];
  const actionableCount = scopedCases.filter((item) => attentionStates.includes(item.case_state)).length;
  const pendingCount = scopedCases.filter((item) => item.case_state === "PENDING_WITHIN_SLA").length;
  const verifiedCount = scopedCases.filter((item) => item.case_state === "RECONCILED").length;
  const invalidCount = scopedCases.filter((item) => item.case_state === "INVALID_INPUT").length;
  const activeFilterCount =
    states.length +
    severities.length +
    codes.length +
    Number(Boolean(owner)) +
    Number(Boolean(minAge)) +
    Number(Boolean(maxAge)) +
    Number(Boolean(minAmount)) +
    Number(Boolean(maxAmount)) +
    Number(aiFilter !== "all") +
    Number(humanFilter !== "all") +
    Number(Boolean(bucket));
  const queueLenses = [
    { label: "All states", count: scopedCases.length, states: [] },
    { label: "Needs action", count: actionableCount, states: attentionStates },
    { label: "Pending", count: pendingCount, states: ["PENDING_WITHIN_SLA"] },
    { label: "Verified", count: verifiedCount, states: ["RECONCILED"] },
    { label: "Invalid", count: invalidCount, states: ["INVALID_INPUT"] },
  ];
  const appliedFilters: Array<{ key: string; label: string; onRemove: () => void }> = [
    ...states.map((state) => ({
      key: `state-${state}`,
      label: `State: ${titleCase(state)}`,
      onRemove: () => applyStates(states.filter((item) => item !== state)),
    })),
    ...severities.map((severity) => ({
      key: `severity-${severity}`,
      label: `Severity: ${titleCase(severity)}`,
      onRemove: () => setSeverities(severities.filter((item) => item !== severity)),
    })),
    ...codes.map((code) => ({
      key: `code-${code}`,
      label: `Code: ${titleCase(code)}`,
      onRemove: () => setCodes(codes.filter((item) => item !== code)),
    })),
    ...(owner
      ? [{ key: "owner", label: `Owner: ${owner}`, onRemove: () => setOwner("") }]
      : []),
    ...(minAge
      ? [{ key: "min-age", label: `Age from ${minAge}d`, onRemove: () => setMinAge("") }]
      : []),
    ...(maxAge
      ? [{ key: "max-age", label: `Age to ${maxAge}d`, onRemove: () => setMaxAge("") }]
      : []),
    ...(minAmount
      ? [{ key: "min-amount", label: `Risk from ₹${minAmount}`, onRemove: () => setMinAmount("") }]
      : []),
    ...(maxAmount
      ? [{ key: "max-amount", label: `Risk to ₹${maxAmount}`, onRemove: () => setMaxAmount("") }]
      : []),
    ...(aiFilter !== "all"
      ? [{ key: "ai", label: aiFilter === "yes" ? "AI-assisted" : "Deterministic only", onRemove: () => applyAI("all") }]
      : []),
    ...(humanFilter !== "all"
      ? [{ key: "human", label: humanFilter === "reviewed" ? "Human reviewed" : "Pending review", onRemove: () => applyHuman("all") }]
      : []),
    ...(bucket
      ? [{ key: "bucket", label: `Cash bucket: ${titleCase(bucket)}`, onRemove: () => applyBucket("") }]
      : []),
  ];

  const columns: DataTableColumn<CaseSummary>[] = [
    {
      key: "case_id",
      label: "Case ID",
      sortValue: (item) => item.case_id,
      render: (item) => (
        <span className="block max-w-[130px] truncate font-mono font-semibold text-[#34413b]" title={item.case_id}>
          {shortId(item.case_id, 16)}
        </span>
      ),
    },
    {
      key: "state",
      label: "Final State",
      sortValue: (item) => item.case_state,
      render: (item) => <StatusBadge compact status={item.case_state} />,
    },
    {
      key: "decision",
      label: "Decision",
      sortValue: (item) => item.decision_level ?? "",
      render: (item) => (
        <span className="text-[0.68rem] font-bold text-[#5d6964]">{titleCase(item.decision_level)}</span>
      ),
    },
    {
      key: "risk",
      label: "Amount at Risk",
      sortValue: (item) => item.amount_at_risk_paise,
      render: (item) => (
        <AmountDisplay
          className={item.amount_at_risk_paise ? "font-bold text-[#ac342f]" : "text-[#6f7a75]"}
          paise={item.amount_at_risk_paise}
        />
      ),
    },
    {
      key: "gross",
      label: "Gross Amount",
      sortValue: (item) => item.gross_amount_paise,
      render: (item) => <AmountDisplay className="font-semibold" paise={item.gross_amount_paise} />,
    },
    {
      key: "net",
      label: "Explained Net",
      sortValue: (item) => item.net_amount_paise,
      render: (item) => <AmountDisplay paise={item.net_amount_paise} />,
    },
    {
      key: "settlement",
      label: "Settlement ID",
      sortValue: (item) => item.settlement_id ?? "",
      render: (item) => (
        <span className="block max-w-[120px] truncate font-mono text-[0.67rem]" title={item.settlement_id ?? ""}>
          {item.settlement_id ? shortId(item.settlement_id, 15) : "—"}
        </span>
      ),
    },
    {
      key: "bank",
      label: "Bank Receipt",
      sortValue: (item) => item.bank_receipt_state ?? "",
      render: (item) => titleCase(item.bank_receipt_state),
    },
    {
      key: "age",
      label: "Age",
      sortValue: (item) => ageDays(item.created_at),
      render: (item) => `${ageDays(item.created_at)}d`,
    },
    {
      key: "exception",
      label: "Exception Code",
      sortValue: (item) => item.exception_code ?? "",
      render: (item) => (
        <span className={`block max-w-[150px] text-[0.66rem] font-semibold ${item.exception_code ? "text-[#9b3732]" : "text-[#84908a]"}`}>
          {item.exception_code ? titleCase(item.exception_code) : "None"}
        </span>
      ),
    },
    {
      key: "owner",
      label: "Owner",
      sortValue: (item) => item.owner_role ?? "",
      render: (item) => (
        <span className="inline-flex items-center gap-1 text-[0.67rem]">
          <UserRound aria-hidden="true" size={11} /> {item.owner_role ?? "Unassigned"}
        </span>
      ),
    },
    {
      key: "ai",
      label: "AI",
      sortValue: (item) => Number(item.ai_assisted),
      render: (item) => (item.ai_assisted ? <AIBadge compact /> : <span className="text-[#909994]">—</span>),
    },
  ];

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Cases &amp; exception queue</p>
          <h1 className="page-title">Economic cases</h1>
          <p className="page-subtitle">
            {formatInteger(filteredCases.length)} of {formatInteger(cases.length)} cases in the current view.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-[6px] border border-[#e2e8f0] bg-white px-3 py-2 text-[0.68rem] font-bold text-[#475569] shadow-[0_1px_2px_rgba(8,18,37,0.04)]">
          <Filter aria-hidden="true" size={14} />
          {activeFilterCount} active {activeFilterCount === 1 ? "filter" : "filters"}
        </div>
      </section>

      <section aria-label="Queue views" className="overflow-x-auto rounded-[8px] border border-[#e2e8f0] bg-white shadow-[0_1px_2px_rgba(8,18,37,0.04)]">
        <div className="grid min-w-[650px] grid-cols-5 divide-x divide-[#e2e8f0]">
          {queueLenses.map((lens) => {
            const active =
              states.length === lens.states.length &&
              lens.states.every((state) => states.includes(state));
            return (
              <button
                aria-pressed={active}
                className={`relative flex min-h-[66px] items-center justify-between gap-3 px-4 text-left transition-colors ${
                  active ? "bg-[#eff6ff]" : "hover:bg-[#f8fafc]"
                }`}
                key={lens.label}
                onClick={() => applyStates(lens.states)}
                type="button"
              >
                <span className={`text-[0.69rem] font-bold ${active ? "text-[#0c44ac]" : "text-[#475569]"}`}>
                  {lens.label}
                </span>
                <strong className={`text-[1rem] tabular-nums ${active ? "text-[#0c44ac]" : "text-[#0f172a]"}`}>
                  {formatInteger(lens.count)}
                </strong>
                <span className={`absolute inset-x-4 bottom-0 h-0.5 rounded-full ${active ? "bg-[#0c44ac]" : "bg-transparent"}`} />
              </button>
            );
          })}
        </div>
      </section>

      <section className="panel relative z-10" aria-label="Case filters">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Queue controls</h2>
            <p className="panel-copy">State, ownership, exposure, and review status</p>
          </div>
          <button className="btn btn-ghost" onClick={resetFilters} type="button">
            <RotateCcw aria-hidden="true" size={14} /> Reset
          </button>
        </div>
        <div className={`flex flex-wrap gap-2 p-3 ${advancedOpen ? "border-b border-[#e2e8f0]" : ""}`}>
          <FilterMenu
            label="State"
            onToggle={(value) =>
              applyStates(
                states.includes(value)
                  ? states.filter((item) => item !== value)
                  : [...states, value],
              )
            }
            options={stateOptions}
            selected={states}
          />
          <FilterMenu
            label="Severity"
            onToggle={(value) => toggle(severities, value, setSeverities)}
            options={severityOptions}
            selected={severities}
          />
          <FilterMenu
            label="Exception code"
            onToggle={(value) => toggle(codes, value, setCodes)}
            options={exceptionCodes}
            selected={codes}
          />
          <label className="relative min-w-[190px] flex-1 sm:max-w-[260px]">
            <span className="sr-only">Search owner</span>
            <Search
              aria-hidden="true"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[#94a3b8]"
              size={14}
            />
            <input
              className="input pl-9"
              onChange={(event) => setOwner(event.target.value)}
              placeholder="Search owner"
              value={owner}
            />
          </label>
          <button className="btn btn-secondary ml-auto" onClick={() => setAdvancedOpen((current) => !current)} type="button">
            <SlidersHorizontal aria-hidden="true" size={14} />
            More filters
            {advancedOpen ? <ChevronUp aria-hidden="true" size={13} /> : <ChevronDown aria-hidden="true" size={13} />}
          </button>
        </div>
        {advancedOpen ? <div className="grid gap-3 bg-[#f8fafc] p-3 sm:grid-cols-2 xl:grid-cols-6">
          <div className="grid grid-cols-2 gap-2">
            <label className="field">
              <span className="field-label">Min age</span>
              <input className="input" min="0" onChange={(event) => setMinAge(event.target.value)} placeholder="0" type="number" value={minAge} />
            </label>
            <label className="field">
              <span className="field-label">Max age</span>
              <input className="input" min="0" onChange={(event) => setMaxAge(event.target.value)} placeholder="Any" type="number" value={maxAge} />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="field">
              <span className="field-label">Min risk ₹</span>
              <input className="input" min="0" onChange={(event) => setMinAmount(event.target.value)} placeholder="0" type="number" value={minAmount} />
            </label>
            <label className="field">
              <span className="field-label">Max risk ₹</span>
              <input className="input" min="0" onChange={(event) => setMaxAmount(event.target.value)} placeholder="Any" type="number" value={maxAmount} />
            </label>
          </div>
          <label className="field">
            <span className="field-label">AI involvement</span>
            <select className="select" onChange={(event) => applyAI(event.target.value)} value={aiFilter}>
              <option value="all">All cases</option>
              <option value="yes">AI-assisted</option>
              <option value="no">Deterministic only</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Human review</span>
            <select className="select" onChange={(event) => applyHuman(event.target.value)} value={humanFilter}>
              <option value="all">All cases</option>
              <option value="reviewed">Reviewed</option>
              <option value="pending">Pending review</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Cash bucket</span>
            <select className="select" onChange={(event) => applyBucket(event.target.value)} value={bucket}>
              <option value="">All buckets</option>
              {cashBuckets.map((item) => (
                <option key={item} value={item}>
                  {titleCase(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Sort queue</span>
            <select className="select" onChange={(event) => setSort(event.target.value)} value={sort}>
              <option value="risk_desc">Amount at risk</option>
              <option value="age_desc">Age descending</option>
              <option value="severity">Severity</option>
              <option value="case_id">Case ID</option>
            </select>
          </label>
        </div> : null}
        {appliedFilters.length ? (
          <div
            aria-label="Applied filters"
            className="flex flex-wrap items-center gap-2 border-t border-[#e2e8f0] bg-[#f8fafc] px-3 py-2.5"
            data-testid="applied-filters"
          >
            <span className="text-[0.65rem] font-bold uppercase text-[#64748b]">Applied</span>
            {appliedFilters.map((filter) => (
              <button
                aria-label={`Remove ${filter.label} filter`}
                className="inline-flex min-h-7 items-center gap-1.5 rounded-[5px] border border-[#cbd5e1] bg-white px-2 text-[0.65rem] font-semibold text-[#334155] hover:border-[#94a3b8] hover:bg-[#f1f5f9]"
                key={filter.key}
                onClick={filter.onRemove}
                title={`Remove ${filter.label} filter`}
                type="button"
              >
                {filter.label}
                <X aria-hidden="true" size={12} />
              </button>
            ))}
            {appliedFilters.length > 1 ? (
              <button className="btn btn-ghost ml-auto min-h-7 px-2" onClick={resetFilters} type="button">
                Clear all
              </button>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="panel overflow-hidden">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Case queue</h2>
            <p className="panel-copy">Select a row to inspect the complete evidence chain</p>
          </div>
          <SlidersHorizontal aria-hidden="true" className="text-[#66736d]" size={17} />
        </div>
        {casesQuery.isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }).map((_, index) => (
              <div className="skeleton h-12" key={index} />
            ))}
          </div>
        ) : casesQuery.error ? (
          <div className="flex min-h-56 flex-col items-center justify-center gap-3 px-5 py-12 text-center text-[0.74rem] text-[#8f3935]" role="alert">
            <span>The case queue could not be loaded. Existing case data remains unchanged.</span>
            <button className="btn btn-secondary" onClick={() => void casesQuery.refetch()} type="button">
              <RotateCcw aria-hidden="true" size={14} /> Retry
            </button>
          </div>
        ) : (
          <DataTable
            columns={columns}
            filterPlaceholder="Search case, settlement, exception, or owner"
            filterText={(item) =>
              [item.case_id, item.settlement_id, item.exception_code, item.owner_role, item.case_state]
                .filter(Boolean)
                .join(" ")
            }
            getRowKey={(item) => item.case_id}
            onRowClick={(item) => setSelectedCaseId(item.case_id)}
            pageSize={15}
            rows={filteredCases}
            testId="cases-table"
          />
        )}
      </section>

      <EvidenceDrawer caseId={selectedCaseId} onClose={() => setSelectedCaseId(null)} runId={runId} />
    </div>
  );
}
