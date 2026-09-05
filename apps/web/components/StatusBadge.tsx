import {
  CheckCircle2,
  CircleHelp,
  CircleSlash2,
  Clock3,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { titleCase } from "@/lib/format";

const styles: Record<string, { className: string; label: string; icon: typeof CheckCircle2 }> = {
  RECONCILED: {
    className: "border-[#a7f3d0] bg-[#ecfdf5] text-[#065f46]",
    label: "Verified",
    icon: CheckCircle2,
  },
  PENDING_WITHIN_SLA: {
    className: "border-[#fde68a] bg-[#fffbeb] text-[#92400e]",
    label: "Pending within SLA",
    icon: Clock3,
  },
  ACTIONABLE_EXCEPTION: {
    className: "border-[#fecdd3] bg-[#fff1f2] text-[#9f1239]",
    label: "Actionable exception",
    icon: ShieldAlert,
  },
  INVALID_INPUT: {
    className: "border-[#e2e8f0] bg-[#f1f5f9] text-[#475569]",
    label: "Invalid input",
    icon: CircleSlash2,
  },
  SUGGESTED_FOR_REVIEW: {
    className: "border-[#c7d2fe] bg-[#eef2ff] text-[#4338ca]",
    label: "Suggested for review",
    icon: Sparkles,
  },
  APPROVED_PENDING_VERIFICATION: {
    className: "border-[#bae6fd] bg-[#f0f9ff] text-[#0369a1]",
    label: "Approved pending verification",
    icon: Clock3,
  },
  DEFERRED: {
    className: "border-[#fed7aa] bg-[#fff7ed] text-[#9a3412]",
    label: "Deferred",
    icon: Clock3,
  },
  REJECTED_SUGGESTION: {
    className: "border-[#e2e8f0] bg-[#f1f5f9] text-[#475569]",
    label: "Rejected suggestion",
    icon: CircleSlash2,
  },
};

export function StatusBadge({ status, compact = false }: { status: string; compact?: boolean }) {
  const config = styles[status] ?? {
    className: "border-[#e2e8f0] bg-[#f8fafc] text-[#475569]",
    label: titleCase(status),
    icon: CircleHelp,
  };
  const Icon = config.icon;
  return (
    <span
      className={`inline-flex min-h-6 items-center gap-1.5 rounded-[6px] border px-2.5 py-1 text-[0.66rem] font-bold leading-none whitespace-nowrap shadow-xs ${config.className}`}
      title={config.label}
    >
      <Icon aria-hidden="true" size={12} strokeWidth={2.2} />
      {compact ? config.label.split(" ")[0] : config.label}
    </span>
  );
}
