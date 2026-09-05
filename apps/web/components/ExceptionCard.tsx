import { ArrowRight, ShieldAlert, UserRound } from "lucide-react";

import { titleCase } from "@/lib/format";
import type { CaseSummary } from "@/lib/api";

import { AIBadge } from "./AIBadge";
import { AmountDisplay } from "./AmountDisplay";

export function ExceptionCard({ caseData }: { caseData: CaseSummary }) {
  return (
    <section className="rounded-[6px] border border-[#edc3c0] bg-[#fffafa] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[5px] bg-[#fdeceb] text-[#b83531]">
            <ShieldAlert aria-hidden="true" size={17} />
          </span>
          <div className="min-w-0">
            <p className="m-0 text-[0.72rem] font-bold text-[#a8332f]">
              {titleCase(caseData.exception_severity)} · {titleCase(caseData.exception_code)}
            </p>
            <p className="mb-0 mt-1 text-[0.82rem] leading-5 text-[#4b514f]">
              {caseData.next_action ?? "Review source evidence and resolve this exception."}
            </p>
          </div>
        </div>
        {caseData.ai_assisted ? <AIBadge /> : null}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-[#edd5d3] pt-3 text-[0.72rem] sm:grid-cols-3">
        <div>
          <span className="block text-[#7b6967]">Amount at risk</span>
          <AmountDisplay className="mt-1 block font-bold text-[#9f2d29]" paise={caseData.amount_at_risk_paise} />
        </div>
        <div>
          <span className="block text-[#7b6967]">Owner</span>
          <span className="mt-1 flex items-center gap-1 font-semibold text-[#4d5451]">
            <UserRound aria-hidden="true" size={12} />
            {caseData.owner_role ?? "Unassigned"}
          </span>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <span className="block text-[#7b6967]">Next step</span>
          <span className="mt-1 flex items-center gap-1 font-semibold text-[#4d5451]">
            <ArrowRight aria-hidden="true" size={12} />
            Human review
          </span>
        </div>
      </div>
    </section>
  );
}

