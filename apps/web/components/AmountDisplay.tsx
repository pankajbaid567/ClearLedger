import { formatPaise } from "@/lib/format";

export function AmountDisplay({
  paise,
  currency = "INR",
  className = "",
  showSign = false,
}: {
  paise: number;
  currency?: string;
  className?: string;
  showSign?: boolean;
}) {
  const sign = showSign && paise > 0 ? "+" : "";
  return (
    <span className={`tabular-nums whitespace-nowrap ${className}`}>
      {sign}
      {formatPaise(paise, currency)}
    </span>
  );
}

