"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { useEffect, useMemo, useState } from "react";

import { AmountDisplay } from "@/components/AmountDisplay";
import { BrandMark } from "@/components/BrandMark";
import { ExportButton } from "@/components/ExportButton";
import { useIdentity } from "@/components/AccessBoundary";
import {
  APIError,
  exportUrl,
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
  const queryClient = useQueryClient();
  const identity = useIdentity();
  const canCreate = identity?.permissions.includes("create") ?? false;
  const [run, setRun] = useState<Run | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [files, setFiles] = useState<Partial<Record<SourceKey, File>>>({});
  const [isDemoRun, setIsDemoRun] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  useEffect(() => {
    setLastRunId(window.localStorage.getItem("clearledger:lastRunId"));
  }, []);

  const demoMutation = useMutation({
    mutationFn: loadDemoRun,
    onSuccess: ({ run: loadedRun, validation: loadedValidation }) => {
      setRun(loadedRun);
      setIsDemoRun(true);
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
      setIsDemoRun(false);
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
      try { await reconcileRun(run.id); }
      catch (error) {
        // A dropped response is not proof the saved run failed.
        const persisted = await getRunStatus(run.id).catch(() => null);
        if (persisted?.status !== "COMPLETED") throw error;
      }
      await waitForPersistedCompletion(run.id);
      return run.id;
    },
    onSuccess: (runId) => {
      if (isDemoRun) {
        void evaluateRun(runId).then(() => Promise.all([
          queryClient.invalidateQueries({ queryKey: ["metrics", runId] }),
          queryClient.invalidateQueries({ queryKey: ["evaluation", runId] }),
        ])).catch(() => { /* Reconciliation is usable even when optional evaluation is unavailable. */ });
      }
      router.push(`/runs/${runId}`);
    },
  });
  const progressQuery = useQuery({
    queryKey: ["run-progress", run?.id],
    queryFn: () => getRunStatus(run!.id),
    enabled: Boolean(run && reconcileMutation.isPending),
    refetchInterval: reconcileMutation.isPending ? 700 : false,
  });
  const busy = demoMutation.isPending || uploadMutation.isPending || reconcileMutation.isPending;
  const sourcesPresent = validation?.required_sources_present ?? (validation ? validation.missing_source_types.length === 0 : false);

  const validationByType = useMemo(
    () => new Map(validation?.files.map((item) => [item.source_type, item]) ?? []),
    [validation],
  );
  const allFilesSelected = sourceTypes.every(({ key }) => files[key]);
  const ready = Boolean(run && (validation?.processing_permitted ?? validation?.valid));
  const presentSourceCount = validation
    ? sourceTypes.length - validation.missing_source_types.length
    : Object.keys(files).length;
  const readinessPercent = Math.round((presentSourceCount / sourceTypes.length) * 100);
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
                  Synthetic demo · Five sources
                </span>
                <button
                  className="btn btn-primary"
                  data-testid="load-demo"
                  disabled={busy || !canCreate}
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
                          result && result.rejected_count === 0 ? "bg-[#ecfdf5] text-[#059669]" : "bg-[#f1f5f9] text-[#64748b]"
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
                        disabled={busy || !canCreate}
                        aria-label={`Choose ${label} CSV`}
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
                disabled={!allFilesSelected || busy || !canCreate}
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

          {reconcileMutation.isPending ? (
            <section className="panel p-5" data-testid="reconciliation-progress" role="status" aria-live="polite">
              <h2 className="panel-title">Reconciliation progress</h2>
              <p className="panel-copy">{progressQuery.data?.stage ? titleCase(progressQuery.data.stage) : "Waiting for persisted run status"} · {progressQuery.data?.processed_records ?? 0} records processed</p>
              <progress className="mt-3 w-full" max={100} value={progressQuery.data?.progress_percent ?? 0} aria-label="Persisted reconciliation progress" />
              {progressQuery.error ? <p className="text-xs text-amber-800">Progress updates are unavailable. The reconciliation request is still in progress.</p> : null}
            </section>
          ) : null}
          {validation ? <section className="panel space-y-3 p-5" aria-labelledby="validation-details">
            <h2 className="panel-title" id="validation-details">Source validation</h2>
            <p className="text-sm">{sourcesPresent ? "All required source files are present." : `Missing sources: ${validation.missing_source_types.map(titleCase).join(", ")}`} {validation.invalid_rows ? `${validation.invalid_rows} rows require correction; they remain visible in the exception record.` : "All source rows passed validation."}</p>
            {validation.files.map((file) => <details className="rounded border border-slate-200 p-3" key={file.source_type}><summary className="cursor-pointer text-sm font-semibold">{titleCase(file.source_type)} · {file.accepted_count} accepted / {file.rejected_count} rejected · {titleCase(file.quality)}</summary>{file.errors.length ? <ul className="mt-3 space-y-2 text-xs">{file.errors.map((issue, index) => <li key={index} className="break-words rounded bg-amber-50 p-2">{Object.entries(issue).map(([key, value]) => `${titleCase(key)}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`).join(" · ")}</li>)}</ul> : <p className="text-xs">No rejected rows.</p>}</details>)}
            {run && validation.invalid_rows > 0 ? <ExportButton href={exportUrl(run.id, "rejected-rows.csv")} label="Download rejected rows CSV" /> : null}
          </section> : null}

        </div>

        <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <section className="panel overflow-hidden">
            <div className="border-b border-[#e2e8f0] p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="eyebrow">Run readiness</p>
                  <h2 className="m-0 text-[1rem] font-bold text-[#0f172a]">
                    {ready
                      ? "Ready to reconcile"
                      : sourcesPresent
                        ? "Sources present · validation blocked"
                        : "Waiting for required sources"}
                  </h2>
                </div>
                <span
                  className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                    sourcesPresent
                      ? "bg-[#ecfdf5] text-[#059669]"
                      : "bg-[#f1f5f9] text-[#64748b]"
                  }`}
                >
                  <CheckCircle2 aria-hidden="true" size={17} />
                </span>
              </div>
              <div className="mt-5 flex items-center justify-between text-[0.64rem] font-bold text-[#64748b]">
                <span>Required source readiness</span>
                <span className="tabular-nums">{readinessPercent}%</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#e2e8f0]">
                <div
                  className={`h-full rounded-full transition-[width] duration-300 ${sourcesPresent ? "bg-[#059669]" : "bg-[#0c44ac]"}`}
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
                <span className="block text-[0.62rem] font-bold text-[#64748b]">Partial files</span>
                <strong className="mt-1 block text-lg text-[#d97706] tabular-nums">
                  {validation?.files.filter((item) => item.quality === "PARTIAL").length ?? 0}
                </strong>
              </div>
              <div className="px-4 py-4">
                <span className="block text-[0.62rem] font-bold text-[#64748b]">Rejected rows</span>
                <strong className="mt-1 block text-lg text-[#64748b] tabular-nums">
                  {validation?.invalid_rows ?? 0}
                </strong>
              </div>
            </div>

            <dl className="space-y-3 p-5 text-[0.69rem]">
              {run?.dataset_checksum ? <div><dt className="text-slate-500">Dataset checksum</dt><dd className="m-0 break-all font-mono text-xs">{run.dataset_checksum}</dd></div> : null}
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
                  {run ? titleCase(progressQuery.data?.status ?? run.status) : "Waiting for data"}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-[#64748b]">Processing permission</dt>
                <dd className="m-0 font-semibold">
                  {ready ? "Permitted" : validation ? "Blocked by validation" : "Not evaluated"}
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
              {error instanceof APIError ? `${error.message}${error.requestId ? ` · Request ${error.requestId}` : ""}${error.retryable ? " Retry when the connection is available." : ""}` : "The operation could not be completed."}
            </p>
          ) : null}

          {!canCreate ? <p className="text-sm text-slate-600">Your role can view runs. Creating or uploading a run requires the create permission.</p> : null}
          <button
            className="btn btn-primary min-h-[48px] w-full text-[0.8rem]"
            data-testid="start-reconciliation"
            disabled={!ready || busy || !canCreate}
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
