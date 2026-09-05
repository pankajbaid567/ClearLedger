"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { accessHeaders } from "@/lib/api";

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportButton({ href, label, testId, digestHeader }: { href: string; label: string; testId?: string; digestHeader?: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [digest, setDigest] = useState<string | null>(null);
  async function download() {
    setPending(true); setError(null); setDigest(null);
    try {
      const response = await fetch(href, { headers: accessHeaders() });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(`${body?.error?.message ?? `Download failed (${response.status})`}${body?.error?.request_id ? ` · Request ${body.error.request_id}` : ""}`);
      }
      const filename = href.split("/").pop() ?? "export";
      const separateDigest = digestHeader ? response.headers.get(digestHeader) : null;
      if (digestHeader && !separateDigest) throw new Error("The server omitted the independent artifact digest.");
      saveBlob(await response.blob(), filename);
      if (separateDigest) {
        saveBlob(new Blob([`${separateDigest}  ${filename}\n`], { type: "text/plain" }), `${filename}.sha256`);
        setDigest(separateDigest);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Download unavailable. Try again."); }
    finally { setPending(false); }
  }
  return <span><button className="btn btn-secondary" data-testid={testId} disabled={pending} onClick={() => void download()} type="button"><Download aria-hidden="true" size={15} />{pending ? "Preparing…" : label}</button>{digest ? <span className="mt-1 block max-w-md break-all font-mono text-[0.62rem] text-slate-600">Separate SHA-256 saved: {digest}</span> : null}{error ? <span role="alert" className="mt-1 block max-w-md text-xs text-red-700">{error} · Retry the download.</span> : null}</span>;
}
