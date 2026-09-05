"use client";

import Link from "next/link";
import type { TaxAuditResponse } from "@/lib/api";
import { formatPaise, formatPercent } from "@/lib/format";

export function TaxAuditCard({ taxAudit, runId }: { taxAudit: TaxAuditResponse; runId: string }) {
  const feeRate = taxAudit.gateway_fee_rate_denominator ? (taxAudit.gateway_fee_rate_numerator ?? 0) / taxAudit.gateway_fee_rate_denominator : null;
  const taxRate = taxAudit.tax_rate_denominator ? (taxAudit.tax_rate_numerator ?? 0) / taxAudit.tax_rate_denominator : null;
  return (
    <section className="panel overflow-hidden" data-testid="tax-audit-card">
      <header className="panel-header"><div><p className="eyebrow">Policy arithmetic only</p><h2 className="panel-title">Gateway fee and tax consistency</h2><p className="panel-copy">Recorded settlement components compared with the configured policy. External tax statement and eligibility evidence are unavailable.</p></div></header>
      <div className="space-y-4 p-4">
        <p className="text-xs text-slate-500">Policy {taxAudit.policy_id ?? "configured policy"} {taxAudit.policy_version ?? ""} · {taxAudit.total_cases_audited} cases inspected · {taxAudit.unmatched_component_count} unmatched components · Fee rate {feeRate === null ? "unavailable" : formatPercent(feeRate, 2)} · Tax on fee {taxRate === null ? "unavailable" : formatPercent(taxRate, 2)}</p>
        <dl className="grid grid-cols-2 gap-3 xl:grid-cols-4">{[
          ["Recorded gateway fees", taxAudit.total_gateway_fee_paise],
          ["Expected gateway fees", taxAudit.expected_gateway_fee_paise],
          ["Recorded tax components", taxAudit.total_tax_paise],
          ["Expected tax components", taxAudit.expected_tax_paise],
        ].map(([label, value]) => <div className="rounded-lg border border-slate-200 p-3" key={String(label)}><dt className="text-xs text-slate-500">{label}</dt><dd className="m-0 mt-2 text-lg font-semibold">{formatPaise(Number(value))}</dd></div>)}</dl>
        <p className="text-sm">Fee consistency: {taxAudit.fee_policy_pass_rate === null ? "Not measured" : formatPercent(taxAudit.fee_policy_pass_rate)} · Tax consistency: {taxAudit.tax_policy_pass_rate === null ? "Not measured" : formatPercent(taxAudit.tax_policy_pass_rate)}. Rates include failed source-link checks for unmatched components. These checks do not establish entitlement to tax credit.</p>
        {taxAudit.discrepancies.length ? <details className="rounded border border-amber-200 bg-amber-50 p-3"><summary className="cursor-pointer text-sm font-semibold">{taxAudit.discrepant_case_count} cases with policy differences · {taxAudit.unmatched_component_count} unmatched components · inspect evidence</summary><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><thead><tr><th className="p-2">Case / payment</th><th className="p-2">Reason</th><th className="p-2">Fee difference</th><th className="p-2">Tax difference</th><th className="p-2">Evidence</th></tr></thead><tbody>{taxAudit.discrepancies.map((item) => <tr key={`${item.case_id}-${item.payment_id}`}><td className="border-t p-2">{item.case_id}<span className="block text-slate-500">{item.payment_id}</span></td><td className="border-t p-2">{item.discrepancy_code === "SOURCE_EVENT_NOT_FOUND" ? "Source payment not found" : "Recorded amount differs from policy"}</td><td className="border-t p-2">{formatPaise(item.fee_variance_paise)}</td><td className="border-t p-2">{formatPaise(item.tax_variance_paise)}</td><td className="border-t p-2"><Link className="font-semibold text-blue-700 underline" href={`/runs/${runId}/cases?case=${encodeURIComponent(item.case_id)}`}>Inspect case</Link></td></tr>)}</tbody></table></div></details> : <p className="text-sm text-slate-600">No differences in the inspected components.</p>}
      </div>
    </section>
  );
}
