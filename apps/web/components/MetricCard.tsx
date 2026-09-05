import type { LucideIcon } from "lucide-react";
import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

type MetricCardProps = {
  label: string;
  value: React.ReactNode;
  detail?: string;
  href?: string;
  icon?: LucideIcon;
  tone?: "default" | "verified" | "pending" | "risk" | "ai";
  testId?: string;
};

const toneStyles = {
  default: {
    accent: "bg-[#0c44ac]",
    icon: "bg-[#ebf3ff] text-[#0c44ac] border border-[#bfdbfe]/50",
  },
  verified: {
    accent: "bg-[#059669]",
    icon: "bg-[#ecfdf5] text-[#059669] border border-[#a7f3d0]/50",
  },
  pending: {
    accent: "bg-[#d97706]",
    icon: "bg-[#fffbeb] text-[#d97706] border border-[#fde68a]/50",
  },
  risk: {
    accent: "bg-[#e11d48]",
    icon: "bg-[#fff1f2] text-[#e11d48] border border-[#fecdd3]/50",
  },
  ai: {
    accent: "bg-[#6366f1]",
    icon: "bg-[#eef2ff] text-[#6366f1] border border-[#c7d2fe]/50",
  },
};

function CardContent({ label, value, detail, icon: Icon, href, tone = "default" }: MetricCardProps) {
  const styles = toneStyles[tone];
  return (
    <div className="relative h-full overflow-hidden">
      <span className={`absolute inset-y-0 left-0 w-[3px] rounded-full ${styles.accent}`} />
      <div className="flex items-start justify-between gap-3">
        <p className="m-0 pl-3 text-[0.7rem] font-bold leading-5 text-[#475569] tracking-wide uppercase">{label}</p>
        {Icon ? (
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-[7px] shadow-xs ${styles.icon}`}>
            <Icon aria-hidden="true" size={16} />
          </span>
        ) : null}
      </div>
      <div className="mt-3 pl-3 text-[1.6rem] font-extrabold leading-none text-[#0f172a] tabular-nums tracking-tight">
        {value}
      </div>
      <div className="mt-3 flex min-h-8 items-end justify-between gap-2 pl-3 text-[0.68rem] leading-4 text-[#64748b]">
        <span>{detail ?? "Open supporting cases"}</span>
        {href ? (
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#f1f5f9] text-[#475569] transition-colors group-hover:bg-[#0c44ac] group-hover:text-white">
            <ArrowUpRight aria-hidden="true" size={12} />
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function MetricCard(props: MetricCardProps) {
  const className =
    "group block min-h-[142px] rounded-[9px] border border-[#e2e8f0] bg-white p-4 shadow-[0_1px_3px_rgba(15,23,42,0.05)] transition-all duration-200 hover:-translate-y-0.5 hover:border-[#0c44ac]/40 hover:shadow-[0_10px_25px_-5px_rgba(12,68,172,0.1)]";
  return props.href ? (
    <Link className={className} data-testid={props.testId} href={props.href}>
      <CardContent {...props} />
    </Link>
  ) : (
    <div className={className} data-testid={props.testId}>
      <CardContent {...props} />
    </div>
  );
}
