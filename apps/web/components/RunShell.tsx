"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Copy,
  FileClock,
  Gauge,
  Plus,
  Scale,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { getRun } from "@/lib/api";
import { shortId, titleCase } from "@/lib/format";

import { BrandMark } from "./BrandMark";
import { ClaimsLedgerModal } from "./ClaimsLedgerModal";

const navItems = [
  { label: "Control Room", mobileLabel: "Overview", segment: "", icon: Gauge },
  { label: "Cases", mobileLabel: "Cases", segment: "/cases", icon: ClipboardList },
  { label: "Cash Position", mobileLabel: "Cash", segment: "/cash", icon: Banknote },
  { label: "Audit", mobileLabel: "Audit", segment: "/audit", icon: FileClock },
];

export function RunShell({ runId, children }: { runId: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const [copied, setCopied] = useState(false);
  const [isClaimsModalOpen, setIsClaimsModalOpen] = useState(false);
  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
  });
  const run = runQuery.data;

  function isActive(segment: string) {
    const target = `/runs/${runId}${segment}`;
    return segment ? pathname.startsWith(target) : pathname === target;
  }

  async function copyRunId() {
    await navigator.clipboard.writeText(runId);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  const desktopNavigation = (
    <nav aria-label="Run navigation" className="space-y-1">
      {navItems.map(({ label, segment, icon: Icon }) => {
        const active = isActive(segment);
        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={`group relative flex min-h-11 items-center gap-3 rounded-[7px] px-3 text-[0.77rem] font-semibold transition-all ${
              active
                ? "bg-[#0c2340] text-white border border-[#1e3a66] shadow-[0_2px_8px_rgba(12,68,172,0.2)]"
                : "text-[#94a3b8] hover:bg-white/[0.05] hover:text-white"
            }`}
            href={`/runs/${runId}${segment}`}
            key={label}
          >
            <span
              className={`absolute inset-y-2 left-0 w-[3px] rounded-r-full ${
                active ? "bg-[#38bdf8] shadow-[0_0_8px_#38bdf8]" : "bg-transparent"
              }`}
            />
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-[6px] ${
                active ? "bg-[#1e3a66] text-[#38bdf8]" : "text-[#64748b] group-hover:text-white"
              }`}
            >
              <Icon aria-hidden="true" size={15} />
            </span>
            <span className="flex-1">{label}</span>
            {active ? <ChevronRight aria-hidden="true" className="text-[#38bdf8]" size={14} /> : null}
          </Link>
        );
      })}
    </nav>
  );

  const mobileNavigation = (
    <nav aria-label="Run navigation" className="grid min-w-[360px] grid-cols-4">
      {navItems.map(({ label, mobileLabel, segment, icon: Icon }) => {
        const active = isActive(segment);
        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={`relative flex min-h-[52px] flex-col items-center justify-center gap-1 text-[0.65rem] font-bold ${
              active ? "text-[#245fda]" : "text-[#68766f]"
            }`}
            href={`/runs/${runId}${segment}`}
            key={label}
          >
            <Icon aria-hidden="true" size={16} />
            {mobileLabel}
            <span
              className={`absolute inset-x-4 bottom-0 h-0.5 rounded-full ${active ? "bg-[#245fda]" : "bg-transparent"}`}
            />
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen bg-[#f8fafc] lg:grid lg:grid-cols-[250px_minmax(0,1fr)]">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[250px] flex-col border-r border-[#1e293b] bg-[#081225] px-3.5 py-4 text-white lg:flex">
        <Link className="flex items-center gap-3 rounded-[7px] px-2 py-1.5 hover:bg-white/[0.04] transition-colors" href="/">
          <BrandMark />
          <span className="min-w-0">
            <strong className="block text-[0.96rem] leading-5 tracking-tight font-bold text-white">ClearLedger</strong>
            <span className="block text-[0.62rem] font-semibold text-[#94a3b8] uppercase tracking-wider">Settlement Control</span>
          </span>
        </Link>

        <div className="my-4 h-px bg-[#1e293b]" />

        <p className="mb-2 px-2 text-[0.59rem] font-bold text-[#64748b] tracking-wider uppercase">Finance Operations</p>
        <section className="mb-4 rounded-[8px] border border-[#1e293b] bg-[#0c1a32] p-3 shadow-xs" aria-label="Current run">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[0.61rem] font-bold text-[#94a3b8] uppercase tracking-wider">Active run</span>
            <button
              aria-label={copied ? "Run ID copied" : "Copy run ID"}
              className="flex h-7 w-7 items-center justify-center rounded-[5px] text-[#94a3b8] hover:bg-white/10 hover:text-white transition-colors"
              onClick={() => void copyRunId()}
              title={copied ? "Copied" : "Copy run ID"}
              type="button"
            >
              {copied ? <Check aria-hidden="true" size={13} className="text-[#38bdf8]" /> : <Copy aria-hidden="true" size={13} />}
            </button>
          </div>
          <span className="mt-1.5 block truncate font-mono text-[0.68rem] font-semibold text-[#f1f5f9]" title={runId}>
            {shortId(runId, 20)}
          </span>
          <span className="mt-2 flex items-center gap-2 text-[0.65rem] font-medium text-[#cbd5e1]">
            <span className="status-dot text-[#10b981]" />
            {run ? titleCase(run.status) : "Loading status"}
          </span>
        </section>

        <button
          className="mb-4 flex min-h-9.5 w-full items-center justify-between rounded-[7px] border border-[#1e3a66] bg-gradient-to-r from-[#0c2340] to-[#0f2d52] px-3 text-[0.73rem] font-bold text-white hover:border-[#2b85ff]/60 hover:shadow-[0_0_12px_rgba(43,133,255,0.2)] transition-all"
          onClick={() => setIsClaimsModalOpen(true)}
          type="button"
        >
          <span className="flex items-center gap-2">
            <Scale aria-hidden="true" className="text-[#38bdf8]" size={14} />
            Claims Ledger
          </span>
          <span className="rounded-full bg-[#10b981]/20 border border-[#10b981]/40 px-2 py-0.5 text-[0.62rem] font-extrabold text-[#34d399]">
            10/10 Verified
          </span>
        </button>

        {desktopNavigation}

        <div className="mt-auto space-y-3">
          <section className="rounded-[8px] border border-[#1e293b] bg-[#0c1a32] p-3 text-[0.64rem] text-[#94a3b8]">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 font-bold text-[#f1f5f9]">
                {run?.ai_model ? <Sparkles aria-hidden="true" size={13} className="text-[#a78bfa]" /> : <Bot aria-hidden="true" size={13} className="text-[#38bdf8]" />}
                {run?.ai_model ? "AI Analyst Ready" : "Deterministic Mode"}
              </span>
              <span className={`status-dot ${run?.ai_model ? "text-[#a78bfa]" : "text-[#10b981]"}`} />
            </div>
            <p className="mb-0 mt-2 leading-4 text-[#94a3b8]">
              {run?.ai_model ?? "Financial verification remains authoritative."}
            </p>
          </section>
          <Link
            className="flex min-h-10 items-center justify-center gap-2 rounded-[7px] border border-[#1e3a66] bg-[#0c2340]/60 text-[0.73rem] font-bold text-white hover:bg-[#0c2340] hover:border-[#2b85ff]/50 transition-all"
            href="/"
          >
            <Plus aria-hidden="true" size={15} />
            New reconciliation
          </Link>
        </div>
      </aside>

      <div className="min-w-0 lg:col-start-2">
        <header className="sticky top-0 z-20 border-b border-[#e2e8f0] bg-white/95 shadow-[0_1px_3px_rgba(15,23,42,0.03)] backdrop-blur-md">
          <div className="flex min-h-[62px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3 lg:hidden">
              <BrandMark compact />
              <div className="min-w-0">
                <strong className="block text-[0.84rem] leading-4 text-[#0f172a]">ClearLedger</strong>
                <span className="block truncate font-mono text-[0.58rem] text-[#64748b]">{shortId(runId, 14)}</span>
              </div>
            </div>

            <div className="hidden min-w-0 items-center gap-2 text-[0.7rem] text-[#64748b] lg:flex">
              <span className="font-semibold">Reconciliations</span>
              <ChevronRight aria-hidden="true" size={13} className="text-[#94a3b8]" />
              <span className="truncate font-mono font-semibold text-[#0f172a]" title={runId}>
                {runId}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#0c44ac] bg-gradient-to-r from-[#0c44ac] to-[#09368b] px-3 py-1.5 text-[0.65rem] font-bold text-white hover:shadow-[0_4px_12px_rgba(12,68,172,0.25)] transition-all shadow-xs"
                onClick={() => setIsClaimsModalOpen(true)}
                title="Open Claims Ledger"
                type="button"
              >
                <Scale aria-hidden="true" size={12} className="text-[#38bdf8]" />
                <span className="hidden sm:inline">Claims Ledger</span>
                <span className="rounded bg-[#082866] border border-[#38bdf8]/40 px-1.5 py-0.5 text-[0.58rem] font-extrabold text-[#38bdf8]">
                  10/10 Verified
                </span>
              </button>
              <span className="hidden items-center gap-1.5 rounded-[6px] border border-[#a7f3d0] bg-[#ecfdf5] px-2.5 py-1.5 text-[0.64rem] font-bold text-[#065f46] sm:inline-flex">
                <CheckCircle2 aria-hidden="true" size={12} />
                {run ? titleCase(run.status) : "Loading"}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-[6px] border px-2.5 py-1.5 text-[0.64rem] font-bold ${
                  run?.ai_model
                    ? "border-[#c7d2fe] bg-[#eef2ff] text-[#4338ca]"
                    : "border-[#e2e8f0] bg-[#f8fafc] text-[#475569]"
                }`}
              >
                {run?.ai_model ? <Sparkles aria-hidden="true" size={12} /> : <Bot aria-hidden="true" size={12} />}
                {run?.ai_model ? "AI Ready" : "Deterministic"}
              </span>
            </div>
          </div>
          <div className="overflow-x-auto border-t border-[#e2e8f0] bg-white px-2 lg:hidden">{mobileNavigation}</div>
        </header>
        <main className="mx-auto w-full max-w-[1680px] p-4 sm:p-6 lg:p-8">{children}</main>
      </div>

      <ClaimsLedgerModal
        isOpen={isClaimsModalOpen}
        onClose={() => setIsClaimsModalOpen(false)}
        runId={runId}
      />
    </div>
  );
}
