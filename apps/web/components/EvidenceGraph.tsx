import { ArrowDown, Bot, CheckCircle2, UserRound } from "lucide-react";

import type { EvidenceGraphData } from "@/lib/api";
import { shortId, titleCase } from "@/lib/format";

import { AmountDisplay } from "./AmountDisplay";

function entityType(id: string): string {
  const prefix = id.split(":")[0]?.split("_")[0] ?? "entity";
  return titleCase(prefix);
}

const entityBadgeColors: Record<string, string> = {
  Order: "text-[#0284c7] bg-[#f0f9ff] border-[#bae6fd]",
  Payment: "text-[#0c44ac] bg-[#ebf3ff] border-[#bfdbfe]",
  Settlement: "text-[#4f46e5] bg-[#eef2ff] border-[#c7d2fe]",
  SettlementComponent: "text-[#7c3aed] bg-[#f5f3ff] border-[#ddd6fe]",
  Bank: "text-[#059669] bg-[#ecfdf5] border-[#a7f3d0]",
  BankTransaction: "text-[#059669] bg-[#ecfdf5] border-[#a7f3d0]",
};

export function EvidenceGraph({ graph }: { graph: EvidenceGraphData }) {
  if (!graph.edges.length) {
    return (
      <div className="rounded-[8px] border border-dashed border-[#cbd5e1] bg-[#f8fafc] px-5 py-10 text-center text-[0.78rem] text-[#64748b]">
        No verified relationship edges are available for this case.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="evidence-graph">
      {graph.edges.map((edge, index) => {
        const ActorIcon = edge.actor_type === "AI" ? Bot : UserRound;
        const srcType = entityType(edge.source_entity_id);
        const tgtType = entityType(edge.target_entity_id);
        const srcColor = entityBadgeColors[srcType] ?? "text-[#475569] bg-[#f1f5f9] border-[#e2e8f0]";
        const tgtColor = entityBadgeColors[tgtType] ?? "text-[#475569] bg-[#f1f5f9] border-[#e2e8f0]";

        return (
          <div key={`${edge.source_entity_id}-${edge.target_entity_id}-${index}`} className="space-y-1.5">
            <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
              <div className="min-w-0 rounded-[7px] border border-[#e2e8f0] bg-white px-3 py-2 shadow-xs">
                <span className={`inline-block rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wider border ${srcColor}`}>
                  {srcType}
                </span>
                <span className="mt-1 block truncate font-mono text-[0.7rem] font-semibold text-[#0f172a]">
                  {shortId(edge.source_entity_id, 20)}
                </span>
              </div>
              <div className="flex flex-col items-center text-[#94a3b8]">
                <CheckCircle2 aria-hidden="true" className="text-[#059669]" size={15} />
                <ArrowDown aria-hidden="true" className="rotate-[-90deg] text-[#0c44ac]" size={15} />
              </div>
              <div className="min-w-0 rounded-[7px] border border-[#e2e8f0] bg-white px-3 py-2 shadow-xs">
                <span className={`inline-block rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wider border ${tgtColor}`}>
                  {tgtType}
                </span>
                <span className="mt-1 block truncate font-mono text-[0.7rem] font-semibold text-[#0f172a]">
                  {shortId(edge.target_entity_id, 20)}
                </span>
              </div>
            </div>
            <div className="mx-auto flex w-[95%] flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-[6px] border border-[#e2e8f0] bg-[#f8fafc] px-3 py-1.5 text-[0.66rem] text-[#475569]">
              <span className="font-bold text-[#0f172a]">{titleCase(edge.relationship_type)}</span>
              <span className="font-mono font-bold text-[#059669]">
                <AmountDisplay paise={edge.allocated_amount_paise} />
              </span>
              <span className="font-mono text-[#64748b]">{edge.rule_id}</span>
              <span className="inline-flex items-center gap-1 font-semibold text-[#475569]">
                <ActorIcon aria-hidden="true" size={11} className={edge.actor_type === "AI" ? "text-[#6366f1]" : "text-[#0c44ac]"} />
                {titleCase(edge.actor_type)}
              </span>
              <span className="font-medium text-[#64748b]">{titleCase(edge.decision_level)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
