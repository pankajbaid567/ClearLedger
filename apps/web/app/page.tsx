"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  FileCheck2,
  FileSpreadsheet,
  History,
  LoaderCircle,
  Play,
  ShieldCheck,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { AmountDisplay } from "@/components/AmountDisplay";
import { BrandMark } from "@/components/BrandMark";
import { ProgressStepper } from "@/components/ProgressStepper";
import {
  APIError,
  createRun,
  evaluateRun,
  getRun,
  getRunStatus,
  loadDemoRun,
  reconcileRun,
  uploadRunFiles,
  validateRun,
  type Run,
  type Validation,
} from "@/lib/api";
import { formatInteger, shortId, titleCase } from "@/lib/format";

const sourceTypes = [
  { key: "orders", label: "Orders" },
  { key: "payments", label: "Payments" },
  { key: "settlements", label: "Settlements" },
  { key: "settlement_components", label: "Settlement components" },
  { key: "bank_transactions", label: "Bank transactions" },
] as const;

const stages = [
  "Ingestion",
  "Validation",
  "Normalization",
  "Matching",
  "Verification",
  "AI Analysis",
  "Cash Position",
  "Complete",
];

type SourceKey = (typeof sourceTypes)[number]["key"];

async function waitForPersistedCompletion(runId: string) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const runStatus = await getRunStatus(runId);
    if (runStatus.status === "COMPLETED") return;
    if (runStatus.status === "FAILED") {
      throw new APIError(
        409,
        "RECONCILIATION_FAILED",
        runStatus.failure_reason ?? "Reconciliation failed before evaluation.",
      );
    }
    await new Promise((resolve) => window.setTimeout(resolve, 150));
  }
  throw new APIError(
    504,
    "RECONCILIATION_COMMIT_TIMEOUT",
    "Reconciliation finished, but its persisted status could not be confirmed. Retry the request.",
  );
}

export default function RunSetupPage() {
  const router = useRouter();
  const [run, setRun] = useState<Run | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [files, setFiles] = useState<Partial<Record<SourceKey, File>>>({});
  const [activeStage, setActiveStage] = useState(-1);
  const [message, setMessage] = useState<string | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(
    () => () => {
      timers.current.forEach((timer) => window.clearInterval(timer));
    },
    [],
  );

  useEffect(() => {
    setLastRunId(window.localStorage.getItem("clearledger:lastRunId"));
  }, []);

  const demoMutation = useMutation({
    mutationFn: loadDemoRun,
    onSuccess: ({ run: loadedRun, validation: loadedValidation }) => {
      setRun(loadedRun);
      setValidation(loadedValidation);
      setMessage("Demo dataset loaded and validated.");
      window.localStorage.setItem("clearledger:lastRunId", loadedRun.id);
      setLastRunId(loadedRun.id);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      const created = await createRun();
      await uploadRunFiles(created.id, files as Record<string, File>);
      const result = await validateRun(created.id);
      return { run: await getRun(created.id), validation: result };
    },
    onSuccess: ({ run: loadedRun, validation: loadedValidation }) => {
      setRun(loadedRun);
      setValidation(loadedValidation);
      setMessage(
        loadedValidation.valid
          ? "Files uploaded and validated."
          : "Validation found blocking source issues.",
      );
      window.localStorage.setItem("clearledger:lastRunId", loadedRun.id);
      setLastRunId(loadedRun.id);
    },
  });

  const reconcileMutation = useMutation({
    mutationFn: async () => {
      if (!run) throw new Error("No validated run is selected.");
      setActiveStage(0);
      const stageTimer = window.setInterval(
        () => setActiveStage((current) => Math.min(6, current + 1)),
        520,
      );
      timers.current.push(stageTimer);
      try {
        await reconcileRun(run.id);
        setActiveStage(6);
        await waitForPersistedCompletion(run.id);
        await evaluateRun(run.id);
        setActiveStage(7);
        await new Promise((resolve) => window.setTimeout(resolve, 350));
        return run.id;
      } finally {
        window.clearInterval(stageTimer);
      }
    },
    onSuccess: (runId) => router.push(`/runs/${runId}`),
    onError: () => setActiveStage(-1),
  });

  const validationByType = useMemo(
    () => new Map(validation?.files.map((item) => [item.source_type, item]) ?? []),
    [validation],
  );
  const allFilesSelected = sourceTypes.every(({ key }) => files[key]);
  const ready = Boolean(run && validation?.valid);
  const readinessPercent = ready ? 100 : Math.round((Object.keys(files).length / sourceTypes.length) * 70);
  const error = demoMutation.error ?? uploadMutation.error ?? reconcileMutation.error;

  return (
    <div className="min-h-screen bg-[#f8fafc]">
      <header className="border-b border-[#e2e8f0] bg-white shadow-[0_1px_2px_rgba(8,18,37,0.03)]">
        <div className="mx-auto flex min-h-[70px] max-w-[1520px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <BrandMark />
            <div>
              <strong className="block text-[0.98rem] leading-5 text-[#081225] font-bold">ClearLedger</strong>
              <span className="block text-[0.63rem] font-medium text-[#64748b]">Settlement control</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {lastRunId ? (
              <Link className="btn btn-secondary hidden sm:inline-flex" href={`/runs/${lastRunId}`}>
                <History aria-hidden="true" size={14} /> Resume last run
              </Link>
            ) : null}
            <span className="inline-flex items-center gap-1.5 rounded-[5px] border border-[#a7f3d0] bg-[#ecfdf5] px-2.5 py-1.5 text-[0.65rem] font-bold text-[#065f46]">
              <ShieldCheck aria-hidden="true" size={13} />
              Deterministic verification
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-[1520px] gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:px-8 lg:py-9">
        <div className="min-w-0 space-y-5">
          <section className="pb-1">
            <p className="eyebrow">New reconciliation</p>
            <h1 className="page-title">Create a reconciliation run</h1>
            <p className="page-subtitle">
              Assemble the five source ledgers, validate control totals, and start deterministic matching.
            </p>
          </section>

          <section className="panel overflow-hidden" aria-labelledby="dataset-heading">
            <div className="panel-header">
              <div>
                <h2 className="panel-title" id="dataset-heading">
                  Source package
                </h2>
                <p className="panel-copy">Five required CSV sources</p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <span className="hidden rounded-full bg-[#f1f5f9] px-2.5 py-1 text-[0.62rem] font-bold text-[#475569] sm:inline-flex">
                  75 cases · 693 rows
                </span>
                <button
                  className="btn btn-primary"
                  data-testid="load-demo"
                  disabled={demoMutation.isPending || reconcileMutation.isPending}
                  onClick={() => demoMutation.mutate()}
                  type="button"
                >
                  {demoMutation.isPending ? (
                    <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
                  ) : (
                    <Database aria-hidden="true" size={15} />
                  )}
                  {demoMutation.isPending ? "Loading..." : "Load demo dataset"}
                </button>
              </div>
            </div>

            <div className="divide-y divide-[#f1f5f9]">
              {sourceTypes.map(({ key, label }) => {
                const result = validationByType.get(key);
                const selectedFile = files[key];
                return (
                  <div
                    className="grid min-h-[78px] items-center gap-3 px-4 py-3 transition-colors hover:bg-[#f8fafc] sm:grid-cols-[minmax(190px,1fr)_130px_160px_120px] sm:px-5"
                    key={key}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[6px] ${
                          result ? "bg-[#ecfdf5] text-[#059669]" : "bg-[#f1f5f9] text-[#64748b]"
                        }`}
                      >
                        {result ? (
                          <FileCheck2 aria-hidden="true" size={17} />
                        ) : (
                          <FileSpreadsheet aria-hidden="true" size={17} />
                        )}
                      </span>
                      <div className="min-w-0">
                        <p className="m-0 text-[0.78rem] font-bold text-[#0f172a]">{label}</p>
                        <p className="mb-0 mt-1 truncate text-[0.65rem] text-[#64748b]">
                          {result?.filename ?? selectedFile?.name ?? "CSV required"}
                        </p>
                      </div>
                    </div>
                    <div className="text-[0.67rem]">
                      <span className="block text-[#64748b]">Detected type</span>
                      <span className="mt-1 block font-bold text-[#0f172a]">
                        {result ? titleCase(result.source_type) : "Waiting"}
                      </span>
                    </div>
                    <div className="text-[0.67rem]">
                      <span className="block text-[#64748b]">Rows / control total</span>
                      <span className="mt-1 block font-bold text-[#0f172a]">
                        {result ? (
                          <>
                            {formatInteger(result.row_count)} ·{" "}
                            <AmountDisplay paise={result.control_total_paise} />
                          </>
                        ) : (
                          "Not validated"
                        )}
                      </span>
                    </div>
                    <label className="btn btn-secondary justify-self-start sm:justify-self-end">
                      <Upload aria-hidden="true" size={14} />
                      <span>{selectedFile ? "Replace" : "Choose"}</span>
                      <input
                        accept=".csv,text/csv"
                        className="sr-only"
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          setFiles((current) => ({ ...current, [key]: file }));
                          setRun(null);
                          setValidation(null);
                          setMessage(null);
                        }}
                        type="file"
                      />
                    </label>
                  </div>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e2e8f0] bg-[#f8fafc] px-4 py-3 sm:px-5">
              <span className="flex items-center gap-2 text-[0.67rem] font-semibold text-[#64748b]">
                <span className="status-dot bg-[#0c44ac]" />
                {Object.keys(files).length} of 5 manual sources selected
              </span>
              <button
                className="btn btn-secondary"
                disabled={!allFilesSelected || uploadMutation.isPending || reconcileMutation.isPending}
                onClick={() => uploadMutation.mutate()}
                type="button"
              >
                {uploadMutation.isPending ? (
                  <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
                ) : (
                  <FileCheck2 aria-hidden="true" size={15} />
                )}
                Upload and validate
              </button>
            </div>
          </section>

          {reconcileMutation.isPending || activeStage >= 0 ? (
            <section className="panel p-5" data-testid="reconciliation-progress">
              <div className="mb-5 flex items-center justify-between gap-4">
                <div>
                  <h2 className="panel-title">Reconciliation progress</h2>
                  <p className="panel-copy">Run {run ? shortId(run.id, 18) : ""}</p>
                </div>
                <span className="text-[0.72rem] font-bold text-[#64748b]">
                  {activeStage >= stages.length - 1 ? "Complete" : "Processing"}
                </span>
              </div>
              <ProgressStepper activeIndex={activeStage} stages={stages} />
            </section>
          ) : null}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <section className="panel overflow-hidden">
            <div className="border-b border-[#e2e8f0] p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="eyebrow">Run readiness</p>
                  <h2 className="m-0 text-[1rem] font-bold text-[#0f172a]">
                    {ready ? "Ready to reconcile" : "Waiting for validated data"}
                  </h2>
                </div>
                <span
                  className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                    ready ? "bg-[#ecfdf5] text-[#059669]" : "bg-[#f1f5f9] text-[#64748b]"
                  }`}
                >
                  <CheckCircle2 aria-hidden="true" size={17} />
                </span>
              </div>
              <div className="mt-5 flex items-center justify-between text-[0.64rem] font-bold text-[#64748b]">
                <span>Source readiness</span>
                <span className="tabular-nums">{readinessPercent}%</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#e2e8f0]">
                <div
                  className={`h-full rounded-full transition-[width] duration-300 ${ready ? "bg-[#059669]" : "bg-[#0c44ac]"}`}
                  style={{ width: `${readinessPercent}%` }}
                />
              </div>
            </div>

            <div className="grid grid-cols-3 divide-x divide-[#e2e8f0] border-b border-[#e2e8f0] bg-[#f8fafc]">
              <div className="px-4 py-4">
                <span className="block text-[0.62rem] font-bold text-[#64748b]">Valid rows</span>
                <strong className="mt-1 block text-lg text-[#059669] tabular-nums">
                  {validation?.files.reduce((sum, item) => sum + item.accepted_count, 0) ?? 0}
                </strong>
              </div>
              <div className="px-4 py-4">
                <span className="block text-[0.62rem] font-bold text-[#64748b]">Partial</span>
                <strong className="mt-1 block text-lg text-[#d97706] tabular-nums">
                  {validation?.files.filter((item) => item.quality === "PARTIAL").length ?? 0}
                </strong>
              </div>
              <div className="px-4 py-4">
                <span className="block text-[0.62rem] font-bold text-[#64748b]">Invalid</span>
                <strong className="mt-1 block text-lg text-[#64748b] tabular-nums">
                  {validation?.invalid_rows ?? 0}
                </strong>
              </div>
            </div>

            <dl className="space-y-3 p-5 text-[0.69rem]">
              <div className="flex justify-between gap-3">
                <dt className="text-[#64748b]">Run ID</dt>
                <dd className="m-0 font-mono font-semibold" title={run?.id}>
                  {run ? shortId(run.id) : "Not created"}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-[#64748b]">Policy</dt>
                <dd className="m-0 font-semibold">
                  {run?.policy_id && run?.policy_version
                    ? `${run.policy_id} ${run.policy_version}`
                    : "Loaded on run creation"}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-[#64748b]">Source rows</dt>
                <dd className="m-0 font-semibold tabular-nums">
                  {formatInteger(validation?.total_rows ?? 0)}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-[#64748b]">Status</dt>
                <dd className="m-0 flex items-center gap-1.5 font-semibold">
                  {ready ? <span className="status-dot bg-[#059669]" /> : null}
                  {run ? titleCase(run.status) : "Waiting for data"}
                </dd>
              </div>
            </dl>
          </section>

          {message ? (
            <div className="flex items-start gap-2 rounded-[7px] border border-[#a7f3d0] bg-[#ecfdf5] px-4 py-3 text-[0.7rem] font-semibold text-[#065f46]" role="status">
              <CheckCircle2 aria-hidden="true" className="mt-0.5 shrink-0" size={15} />
              <span>{message}</span>
            </div>
          ) : null}
          {error ? (
            <p
              className="rounded-[5px] border border-[#fecdd3] bg-[#fff1f2] px-4 py-3 text-[0.74rem] leading-5 text-[#e11d48]"
              role="alert"
            >
              {error instanceof APIError ? error.message : "The operation could not be completed."}
            </p>
          ) : null}

          <button
            className="btn btn-primary min-h-[48px] w-full text-[0.8rem]"
            data-testid="start-reconciliation"
            disabled={!ready || reconcileMutation.isPending}
            onClick={() => reconcileMutation.mutate()}
            type="button"
          >
            {reconcileMutation.isPending ? (
              <LoaderCircle aria-hidden="true" className="animate-spin" size={17} />
            ) : (
              <Play aria-hidden="true" size={17} />
            )}
            {reconcileMutation.isPending ? "Reconciling..." : "Start reconciliation"}
            {!reconcileMutation.isPending ? <ArrowRight aria-hidden="true" size={16} /> : null}
          </button>
        </aside>
      </main>
    </div>
  );
}
