"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useRef } from "react";

import { exportUrl, getEvaluation, getRun } from "@/lib/api";
import { formatPercent, titleCase } from "@/lib/format";
import { useDialogFocus } from "@/lib/useDialogFocus";
import { ErrorState } from "./ErrorState";
import { ExportButton } from "./ExportButton";

export function ClaimsLedgerModal({ isOpen, onClose, runId }: { isOpen: boolean; onClose: () => void; runId: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useDialogFocus(ref, isOpen, onClose);
  const evaluation = useQuery({ queryKey: ["evaluation", runId], queryFn: () => getEvaluation(runId), enabled: isOpen });
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => getRun(runId), enabled: isOpen });
  if (!isOpen) return null;
  const aggregate = evaluation.data?.aggregate;
  const number = (key: string) => typeof aggregate?.[key] === "number" ? aggregate[key] as number : undefined;
  const claims = [
    { name: "Relationship precision", key: "relationship_precision", threshold: "100%", pass: (n: number) => n === 1, format: formatPercent, denominator: `${number("relationship_true_positive_count") ?? "—"} correct / ${number("relationship_predicted_count") ?? "—"} predicted relationships` },
    { name: "Relationship recall", key: "relationship_recall", threshold: "≥95%", pass: (n: number) => n >= .95, format: formatPercent, denominator: `${number("relationship_true_positive_count") ?? "—"} found / ${number("relationship_expected_count") ?? "—"} expected relationships` },
    { name: "False-positive cases", key: "false_positive_count", threshold: "0", pass: (n: number) => n === 0, format: String, denominator: "Against this dataset’s evaluation truth" },
    { name: "Missing truth cases", key: "missing_case_count", threshold: "0", pass: (n: number) => n === 0, format: String, denominator: "Truth cases without any predicted case" },
    { name: "Unexplained reconciled residual", key: "unexplained_residual_paise", threshold: "0 paise", pass: (n: number) => n === 0, format: (n: number) => `${n} paise`, denominator: "Evaluated reconciled cases only" },
  ];
  const measured = claims.filter((c) => number(c.key) !== undefined);
  const passed = measured.filter((c) => c.pass(number(c.key)!));
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/70 p-3">
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="claims-ledger-title" data-testid="claims-ledger-modal" className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b p-5">
          <div><p className="eyebrow">Run evidence</p><h2 id="claims-ledger-title" className="m-0 text-xl font-bold">Claims Ledger</h2><p className="panel-copy">Measured results for this run; unavailable checks remain unverified.</p></div>
          <button type="button" className="btn btn-secondary btn-icon" aria-label="Close Claims Ledger" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="space-y-5 overflow-y-auto p-5">
          {evaluation.isLoading ? <p role="status">Loading evaluation evidence…</p> : evaluation.error ? <ErrorState title="Evaluation unavailable" message={evaluation.error.message} error={evaluation.error} onRetry={() => void evaluation.refetch()} /> : !evaluation.data ? <p role="status" className="rounded border border-amber-200 bg-amber-50 p-4">Not evaluated. This run has no matching ground-truth evaluation. Reconciliation results and exceptions remain available; precision and recall are unknown.</p> : <>
            <p className="text-sm" role="status">{passed.length} of {measured.length} measured checks passed · {claims.length - measured.length} unavailable · Dataset {evaluation.data.dataset_id}</p>
            <p className="rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">Engine baseline evaluation · execution {evaluation.data.execution_revision}, measured at review revision {evaluation.data.evaluated_review_revision}; current review revision {evaluation.data.current_review_revision}. Human review changes the current projection without rewriting this baseline score.</p>
            <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Evaluation acceptance checks</caption><thead><tr>{["Check", "Measured", "Threshold", "Result"].map((t) => <th className="border-b p-2" key={t}>{t}</th>)}</tr></thead><tbody>{claims.map((c) => { const value = number(c.key); return <tr key={c.key}><th scope="row" className="border-b p-2 font-medium">{c.name}<span className="block text-xs font-normal text-slate-500">{c.denominator}</span></th><td className="border-b p-2">{value === undefined ? "Unavailable" : c.format(value)}</td><td className="border-b p-2">{c.threshold}</td><td className={`border-b p-2 font-semibold ${value === undefined ? "text-slate-600" : c.pass(value) ? "text-emerald-700" : "text-red-700"}`}>{value === undefined ? "NOT RUN" : c.pass(value) ? "PASS" : "FAIL"}</td></tr>; })}</tbody></table></div>
            <section><h3 className="text-base font-bold">Measured scenario breakdown</h3><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Scenario</th><th className="p-2">Precision</th><th className="p-2">Recall</th><th className="p-2">Cases</th></tr></thead><tbody>{Object.entries(evaluation.data.scenario_breakdown).map(([name, row]) => <tr key={name}><th scope="row" className="border-t p-2 font-medium">{titleCase(name)}</th>{["relationship_precision", "relationship_recall", "total_truth_cases"].map((key) => <td className="border-t p-2" key={key}>{typeof row[key] === "number" ? key === "total_truth_cases" ? row[key] as number : formatPercent(row[key] as number) : "Unavailable"}</td>)}</tr>)}</tbody></table></div></section>
            <div className="flex flex-wrap gap-2"><ExportButton href={exportUrl(runId, "evaluation.json")} label="Evaluation JSON" /><ExportButton href={exportUrl(runId, "evaluation.md")} label="Evaluation report" /></div>
          </>}
          <dl className="space-y-2 break-all rounded bg-slate-50 p-4 text-xs"><div><dt className="font-bold">Dataset checksum</dt><dd className="m-0 font-mono">{run.data?.dataset_checksum ?? "Unavailable"}</dd></div><div><dt className="font-bold">Execution / review revision</dt><dd className="m-0">{run.data?.execution_revision ?? "—"} / {run.data?.review_revision ?? "—"}</dd></div><div><dt className="font-bold">Completed at</dt><dd className="m-0">{run.data?.completed_at ?? "Not complete"}</dd></div></dl>
          <p className="text-xs text-slate-600">Precision and recall require matching evaluation truth. Repository reproducibility and stress benchmarks are separate checks: run <code>make verify-claims</code> and inspect their generated reports. This view does not certify tax eligibility, provider availability, or unseen datasets.</p>
        </div>
      </div>
    </div>
  );
}
