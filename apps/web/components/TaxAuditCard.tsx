"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileCheck,
  Receipt,
  Scale,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AmountDisplay } from "@/components/AmountDisplay";
import type { TaxAuditResponse } from "@/lib/api";
import { formatInteger, formatPaise, formatPercent } from "@/lib/format";

interface TaxAuditCardProps {
  taxAudit: TaxAuditResponse;
  runId: string;
}

export function TaxAuditCard({ taxAudit, runId }: TaxAuditCardProps) {
  const [showDiscrepancies, setShowDiscrepancies] = useState(false);
  const hasDiscrepancies = taxAudit.discrepancies.length > 0;

  return (
    <section className="panel min-w-0 overflow-hidden" data-testid="tax-audit-card">
      <div className="panel-header flex-wrap items-center justify-between gap-4 bg-[#f8fafc]">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <span className="eyebrow mb-0 text-[#6366f1]">Tax-Line & ITC Audit</span>
            {taxAudit.itc_status === "AUDIT_READY" ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-[#ecfdf5] border border-[#a7f3d0] px-2.5 py-0.5 text-[0.62rem] font-bold text-[#065f46]">
                <ShieldCheck size={12} /> GSTR-2B Audit Ready
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-[#fff1f2] border border-[#fecdd3] px-2.5 py-0.5 text-[0.62rem] font-bold text-[#e11d48]">
                <ShieldAlert size={12} /> Discrepancies Flagged
              </span>
            )}
          </div>
          <h2 className="panel-title text-[1.05rem] font-bold">
            Gateway Fee & Input Tax Credit (ITC) Audit
          </h2>
          <p className="panel-copy">
            Reconciles 2.0% MDR gateway processing fees and 18.0% GST against claimable Input Tax
            Credit under GSTR-2B.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-[6px] border border-[#e0e7ff] bg-[#eef2ff] px-3 py-1.5 text-[0.7rem] font-semibold text-[#4338ca]">
            MDR: <strong>2.00%</strong> · GST: <strong>18.00%</strong>
          </span>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* 4-Metric Grid */}
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <div className="rounded-[8px] border border-[#e2e8f0] bg-[#f8fafc] p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-[#64748b]">
              <span className="text-[0.68rem] font-bold uppercase tracking-wider">
                Gross Volume
              </span>
              <Receipt size={15} />
            </div>
            <AmountDisplay
              className="mt-2 block text-[1.35rem] font-extrabold text-[#0f172a]"
              paise={taxAudit.gross_payment_volume_paise}
            />
            <p className="mb-0 mt-1 text-[0.68rem] text-[#64748b]">
              Total payments processed
            </p>
          </div>

          <div className="rounded-[8px] border border-[#e2e8f0] bg-[#f8fafc] p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-[#64748b]">
              <span className="text-[0.68rem] font-bold uppercase tracking-wider">
                MDR Fees Deducted
              </span>
              <Scale size={15} />
            </div>
            <AmountDisplay
              className="mt-2 block text-[1.35rem] font-extrabold text-[#d97706]"
              paise={taxAudit.total_gateway_fee_paise}
            />
            <p className="mb-0 mt-1 text-[0.68rem] text-[#64748b]">
              Contracted rate: 2.00%
            </p>
          </div>

          <div className="rounded-[8px] border border-[#e2e8f0] bg-[#f8fafc] p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-[#64748b]">
              <span className="text-[0.68rem] font-bold uppercase tracking-wider">
                GST Deducted (18%)
              </span>
              <FileCheck size={15} />
            </div>
            <AmountDisplay
              className="mt-2 block text-[1.35rem] font-extrabold text-[#0f172a]"
              paise={taxAudit.total_tax_paise}
            />
            <p className="mb-0 mt-1 text-[0.68rem] text-[#64748b]">
              9% CGST + 9% SGST / IGST
            </p>
          </div>

          <div className="rounded-[8px] border border-[#a7f3d0] bg-[#ecfdf5] p-3.5 shadow-xs">
            <div className="flex items-center justify-between text-[#065f46]">
              <span className="text-[0.68rem] font-bold uppercase tracking-wider text-[#065f46]">
                Claimable GSTR-2B ITC
              </span>
              <CheckCircle2 size={15} />
            </div>
            <AmountDisplay
              className="mt-2 block text-[1.35rem] font-extrabold text-[#059669]"
              paise={taxAudit.claimable_itc_paise}
            />
            <p className="mb-0 mt-1 text-[0.68rem] font-medium text-[#047857]">
              Verified eligible tax credit
            </p>
          </div>
        </div>

        {/* Policy Invariant Status Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[6px] border border-[#e2e8f0] bg-[#f8fafc] p-3 text-[0.74rem]">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="font-mono font-bold text-[#0f172a]">INV-TAX-001</span>
              <span className="text-[#64748b]">(18% GST On Fee):</span>
              <strong className="text-[#059669]">
                {formatPercent(taxAudit.tax_policy_pass_rate)}
              </strong>
            </div>
            <span className="text-[#cbd5e1]">|</span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono font-bold text-[#0f172a]">INV-FEE-001</span>
              <span className="text-[#64748b]">(2.0% MDR Rate):</span>
              <strong className="text-[#059669]">
                {formatPercent(taxAudit.fee_policy_pass_rate)}
              </strong>
            </div>
          </div>

          <span className="text-[0.68rem] text-[#64748b]">
            {formatInteger(taxAudit.total_cases_audited)} cases audited across all payment batches
          </span>
        </div>

        {/* Discrepancy Alert Banner */}
        {hasDiscrepancies ? (
          <div
            className="rounded-[8px] border border-[#fecdd3] bg-[#fff1f2] p-4 text-[0.76rem] text-[#9f1239] shadow-xs"
            role="alert"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2.5">
                <AlertTriangle className="mt-0.5 shrink-0 text-[#e11d48]" size={17} />
                <div>
                  <h4 className="m-0 text-[0.82rem] font-bold text-[#9f1239]">
                    {taxAudit.discrepant_case_count} Gateway Fee & Tax Variance Cases Flagged
                  </h4>
                  <p className="mb-0 mt-1 leading-relaxed text-[#881337]">
                    The gateway deducted an excess of{" "}
                    <strong>{formatPaise(taxAudit.fee_variance_paise)}</strong> in fees and{" "}
                    <strong>{formatPaise(taxAudit.disputed_tax_paise)}</strong> in GST beyond
                    contracted policy rates. Disputed tax is excluded from automated GSTR-2B
                    claims until credit notes are issued.
                  </p>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                <Link
                  className="btn btn-secondary border-[#f43f5e]/30 bg-white text-[0.7rem] font-bold text-[#be123c] hover:bg-[#fff1f2]"
                  href={`/runs/${runId}/cases?code=FEE_VARIANCE`}
                >
                  Inspect Cases <ArrowUpRight size={13} />
                </Link>
                <button
                  className="flex items-center gap-1 rounded-[6px] border border-[#fecdd3] bg-white px-2.5 py-1.5 text-[0.7rem] font-semibold text-[#be123c] hover:bg-[#fff1f2]"
                  onClick={() => setShowDiscrepancies(!showDiscrepancies)}
                  type="button"
                >
                  {showDiscrepancies ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  {showDiscrepancies ? "Hide Breakdown" : "View Breakdown"}
                </button>
              </div>
            </div>

            {/* Collapsible Discrepancy Table */}
            {showDiscrepancies ? (
              <div className="mt-3 overflow-x-auto rounded-[6px] border border-[#fecdd3] bg-white">
                <table className="w-full text-left text-[0.72rem]">
                  <thead>
                    <tr className="border-b border-[#fecdd3] bg-[#fff1f2] text-[0.66rem] font-bold text-[#9f1239]">
                      <th className="px-3 py-2">Case ID</th>
                      <th className="px-3 py-2">Payment ID</th>
                      <th className="px-3 py-2 text-right">Gross Amount</th>
                      <th className="px-3 py-2 text-right">Expected Fee</th>
                      <th className="px-3 py-2 text-right">Actual Fee</th>
                      <th className="px-3 py-2 text-right">Fee Diff</th>
                      <th className="px-3 py-2 text-right">Expected GST</th>
                      <th className="px-3 py-2 text-right">Actual GST</th>
                      <th className="px-3 py-2 text-right">GST Diff</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ffe4e6]">
                    {taxAudit.discrepancies.map((disc) => (
                      <tr className="hover:bg-[#fff1f2]/50 transition-colors" key={disc.payment_id}>
                        <td className="px-3 py-2 font-mono font-bold text-[#0f172a]">
                          <Link
                            className="text-[#0c44ac] hover:text-[#09368b] hover:underline"
                            href={`/runs/${runId}/cases?search=${disc.case_id}`}
                          >
                            {disc.case_id}
                          </Link>
                        </td>
                        <td className="px-3 py-2 font-mono text-[#64748b]">{disc.payment_id}</td>
                        <td className="px-3 py-2 text-right font-medium">
                          {formatPaise(disc.gross_amount_paise)}
                        </td>
                        <td className="px-3 py-2 text-right text-[#64748b]">
                          {formatPaise(disc.expected_fee_paise)}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-[#d97706]">
                          {formatPaise(disc.actual_fee_paise)}
                        </td>
                        <td className="px-3 py-2 text-right font-extrabold text-[#e11d48]">
                          +{formatPaise(disc.fee_variance_paise)}
                        </td>
                        <td className="px-3 py-2 text-right text-[#64748b]">
                          {formatPaise(disc.expected_tax_paise)}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-[#0f172a]">
                          {formatPaise(disc.actual_tax_paise)}
                        </td>
                        <td className="px-3 py-2 text-right font-extrabold text-[#e11d48]">
                          +{formatPaise(disc.tax_variance_paise)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
