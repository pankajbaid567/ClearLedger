import { ArrowUpRight, Building2, CircleHelp, Clock3, ReceiptText, ShieldAlert } from "lucide-react";
import Link from "next/link";

import { AmountDisplay } from "./AmountDisplay";

const bucketConfig = {
  BANK_CONFIRMED: {
    icon: Building2,
    accent: "bg-[#059669]",
    iconClass: "bg-[#ecfdf5] text-[#059669] border border-[#a7f3d0]",
  },
  SETTLEMENT_CONFIRMED_IN_TRANSIT: {
    icon: Clock3,
    accent: "bg-[#d97706]",
    iconClass: "bg-[#fffbeb] text-[#d97706] border border-[#fde68a]",
  },
  EXPECTED_SETTLEMENT: {
    icon: ReceiptText,
    accent: "bg-[#0284c7]",
    iconClass: "bg-[#f0f9ff] text-[#0284c7] border border-[#bae6fd]",
  },
  AT_RISK: {
    icon: ShieldAlert,
    accent: "bg-[#e11d48]",
    iconClass: "bg-[#fff1f2] text-[#e11d48] border border-[#fecdd3]",
  },
  UNRESOLVED: {
    icon: CircleHelp,
    accent: "bg-[#64748b]",
    iconClass: "bg-[#f1f5f9] text-[#64748b] border border-[#cbd5e1]",
  },
};

export function CashBucketCard({
  bucket,
  label,
  description,
  amountPaise,
  caseCount,
  href,
  selected = false,
  onClick,
}: {
  bucket: keyof typeof bucketConfig;
  label: string;
  description: string;
  amountPaise: number;
  caseCount: number;
  href: string;
  selected?: boolean;
  onClick?: () => void;
}) {
  const config = bucketConfig[bucket];
  const Icon = config.icon;
  return (
    <Link onClick={onClick}
      aria-current={selected ? "true" : undefined}
      className={`group relative block min-h-[176px] overflow-hidden rounded-[9px] border bg-white p-4 shadow-xs transition-all duration-200 hover:-translate-y-0.5 hover:border-[#0c44ac]/40 hover:shadow-[0_10px_25px_-5px_rgba(12,68,172,0.1)] ${
        selected ? "border-[#0c44ac] ring-2 ring-[#0c44ac]/20 shadow-[0_4px_14px_rgba(12,68,172,0.12)]" : "border-[#e2e8f0]"
      }`}
      data-testid={`cash-bucket-${bucket}`}
      href={href}
    >
      <span className={`absolute inset-x-0 top-0 h-[3px] ${config.accent}`} />
      <div className="flex items-center justify-between gap-2">
        <span className={`flex h-8 w-8 items-center justify-center rounded-[7px] shadow-xs ${config.iconClass}`}>
          <Icon aria-hidden="true" size={16} />
        </span>
        <span className="flex items-center gap-2">
          <span className="rounded-full bg-[#f1f5f9] px-2 py-0.5 text-[0.62rem] font-bold text-[#475569] tabular-nums border border-[#e2e8f0]">
            {caseCount} cases
          </span>
          <ArrowUpRight aria-hidden="true" className="text-[#94a3b8] transition-colors group-hover:text-[#0c44ac]" size={14} />
        </span>
      </div>
      <p className="mb-0 mt-3 text-[0.72rem] font-bold uppercase tracking-wider text-[#475569]">{label}</p>
      <AmountDisplay className="mt-2 block text-[1.35rem] font-extrabold text-[#0f172a] tracking-tight" paise={amountPaise} />
      <p className="mb-0 mt-2 text-[0.67rem] leading-4 text-[#64748b]">{description}</p>
    </Link>
  );
}
