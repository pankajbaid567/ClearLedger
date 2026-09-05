"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { accessHeaders } from "@/lib/api";

function triggerDirectDownload(url: string, headers: Record<string, string>) {
  fetch(url, { headers })
    .then((res) => {
      if (!res.ok) throw new Error(`Download failed: ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const blobUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = url.split("/").pop() ?? "download";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    })
    .catch((err) => console.error("Download failed:", err));
}

export function ExportButton({ href, label, testId, digestHeader, sidecarUrl }: { href: string; label: string; testId?: string; digestHeader?: string; sidecarUrl?: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [digest, setDigest] = useState<string | null>(null);
  async function download() {
    setPending(true); setError(null); setDigest(null);
    try {
      const headers = accessHeaders();
      const response = await fetch(href, { headers });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(`${body?.error?.message ?? `Download failed (${response.status})`}${body?.error?.request_id ? ` · Request ${body.error.request_id}` : ""}`);
      }
      const filename = href.split("/").pop() ?? "export";
      const separateDigest = digestHeader ? response.headers.get(digestHeader) : null;
      if (digestHeader && !separateDigest) throw new Error("The server omitted the independent artifact digest.");
      
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      
      if (sidecarUrl) {
        // Download the sidecar from a separate endpoint after a small delay
        await new Promise((resolve) => setTimeout(resolve, 150));
        triggerDirectDownload(sidecarUrl, headers);
        if (separateDigest) setDigest(separateDigest);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Download unavailable. Try again."); }
    finally { setPending(false); }
  }
  return <span><button className="btn btn-secondary" data-testid={testId} disabled={pending} onClick={() => void download()} type="button"><Download aria-hidden="true" size={15} />{pending ? "Preparing…" : label}</button>{digest ? <span className="mt-1 block max-w-md break-all font-mono text-[0.62rem] text-slate-600">Separate SHA-256 saved: {digest}</span> : null}{error ? <span role="alert" className="mt-1 block max-w-md text-xs text-red-700">{error} · Retry the download.</span> : null}</span>;
}
