import { Sparkles } from "lucide-react";

export function AIBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span
      className="inline-flex min-h-6 items-center gap-1 rounded-[5px] border border-[#ddcfeb] bg-[#f4effa] px-2 py-1 text-[0.64rem] font-bold text-[#6d4a96]"
      title="AI generated a non-authoritative analysis for this case"
    >
      <Sparkles aria-hidden="true" size={12} strokeWidth={2.2} />
      {compact ? "AI" : "AI-assisted"}
    </span>
  );
}
