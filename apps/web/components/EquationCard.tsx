import { CheckCircle2, XCircle } from "lucide-react";

import { AmountDisplay } from "./AmountDisplay";

export type EquationLine = {
  label: string;
  id?: string;
  amountPaise: number;
  sign?: "credit" | "debit" | "neutral";
  passed?: boolean;
};

export function EquationCard({
  lines,
  netSettlementPaise,
  bankCreditPaise,
  bankVerified = false,
  residualPaise,
}: {
  lines: EquationLine[];
  netSettlementPaise: number;
  bankCreditPaise: number | null;
  bankVerified?: boolean;
  residualPaise: number;
}) {
  const residualPassed = residualPaise === 0;
  return (
    <section className="rounded-[8px] border border-[#e2e8f0] bg-white shadow-xs overflow-hidden" data-testid="equation-card">
      <div className="border-b border-[#e2e8f0] bg-[#f8fafc] px-4 py-3">
        <h3 className="m-0 text-[0.85rem] font-bold text-[#0f172a]">Settlement equation</h3>
        <p className="mb-0 mt-1 text-[0.7rem] text-[#64748b]">
          Component arithmetic compared with observed bank credit.
        </p>
      </div>
      <div className="p-4 font-mono text-[0.75rem] space-y-1">
        {lines.length ? (
          lines.map((line, index) => (
            <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-1.5" key={line.id ?? `${line.label}-${index}`}>
              <span className="truncate text-[#334155]">{line.label}</span>
              <AmountDisplay
                className={line.sign === "debit" ? "text-[#e11d48] font-bold" : "text-[#059669] font-bold"}
                paise={line.sign === "debit" ? -Math.abs(line.amountPaise) : line.amountPaise}
                showSign={line.sign === "credit"}
              />
              {line.passed === false ? (
                <XCircle aria-label="Failed" className="text-[#e11d48]" size={15} />
              ) : line.passed === true ? (
                <CheckCircle2 aria-label="Passed" className="text-[#059669]" size={15} />
              ) : <span className="text-[0.6rem] text-slate-500">Recorded</span>}
            </div>
          ))
        ) : (
          <p className="my-2 font-sans text-[0.75rem] text-[#64748b]">No component detail is available.</p>
        )}
        <div className="my-2 border-t border-dashed border-[#cbd5e1]" />
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-1.5 font-bold text-[#0f172a]">
          <span>Net Settlement</span>
          <AmountDisplay paise={netSettlementPaise} />
          <CheckCircle2 aria-label="Calculated" className="text-[#059669]" size={15} />
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-1.5 font-bold text-[#0f172a]">
          <span>Bank Credit</span>
          {bankCreditPaise === null ? <span className="text-xs text-amber-800">No verified bank receipt</span> : <AmountDisplay paise={bankCreditPaise} />}
          {bankVerified && bankCreditPaise !== null && bankCreditPaise === netSettlementPaise ? (
            <CheckCircle2 aria-label="Matched" className="text-[#059669]" size={15} />
          ) : (
            <span className="text-[0.6rem] text-slate-500">Unverified</span>
          )}
        </div>
        <div
          className={`mt-2.5 grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 rounded-[6px] px-3 py-2 font-bold ${
            residualPassed
              ? "border border-[#a7f3d0] bg-[#ecfdf5] text-[#065f46]"
              : "border border-[#fecdd3] bg-[#fff1f2] text-[#9f1239]"
          }`}
        >
          <span className="uppercase tracking-wider text-[0.72rem]">Residual</span>
          <AmountDisplay paise={residualPaise} />
          {residualPassed ? (
            <CheckCircle2 aria-label="Zero residual" size={16} />
          ) : (
            <XCircle aria-label="Residual remains" size={16} />
          )}
        </div>
      </div>
    </section>
  );
}
