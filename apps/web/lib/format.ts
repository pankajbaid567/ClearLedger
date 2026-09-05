import { differenceInCalendarDays, format, formatDistanceToNowStrict } from "date-fns";

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const integer = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function formatPaise(paise: number, currency = "INR"): string {
  if (currency === "INR") return inr.format(paise / 100);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(paise / 100);
}

export function formatInteger(value: number): string {
  return integer.format(value);
}

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDuration(seconds: number): string {
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(2)} s`;
}

export function formatDateTime(value: string): string {
  return format(new Date(value), "dd MMM yyyy, HH:mm:ss");
}

export function relativeTime(value: string): string {
  return formatDistanceToNowStrict(new Date(value), { addSuffix: true });
}

export function ageDays(value: string): number {
  return Math.max(0, differenceInCalendarDays(new Date(), new Date(value)));
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "Not available";
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function shortId(value: string, length = 12): string {
  return value.length <= length ? value : `${value.slice(0, length)}...`;
}

export function metricNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

