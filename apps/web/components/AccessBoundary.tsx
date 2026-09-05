"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useState } from "react";

import { getAccessConfig, getIdentity, setAccessToken, type Identity } from "@/lib/api";

import { ErrorState } from "./ErrorState";

const IdentityContext = createContext<Identity | null>(null);
export function useIdentity() { return useContext(IdentityContext); }

export function AccessBoundary({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const [attempt, setAttempt] = useState(0);
  const config = useQuery({ queryKey: ["access-config"], queryFn: getAccessConfig, retry: false });
  const identity = useQuery({
    queryKey: ["identity", attempt], queryFn: getIdentity,
    enabled: Boolean(config.data && (!config.data.authentication_required || attempt > 0)), retry: false,
  });
  if (config.isLoading || identity.isLoading) return <p className="p-8" role="status">Connecting to ClearLedger…</p>;
  if (config.error) return <ErrorState title="Cannot connect to ClearLedger" message={config.error.message} error={config.error} onRetry={() => void config.refetch()} />;
  if (config.data?.mode === "local_demo" && identity.error) return <ErrorState title="Demo session unavailable" message={identity.error.message} error={identity.error} onRetry={() => void identity.refetch()} />;
  if (!identity.data) return (
    <main className="mx-auto max-w-lg p-6 sm:py-20">
      <h1 className="page-title">Sign in to ClearLedger</h1>
      <p className="page-subtitle">Shared workspace · Enter the access token issued by your administrator. It is kept only in this tab’s memory.</p>
      <form className="panel mt-5 space-y-4 p-5" onSubmit={(event) => {
        event.preventDefault(); setAccessToken(token.trim()); setToken(""); setAttempt((n) => n + 1);
      }}>
        <label className="field">Access token<input autoComplete="off" className="input" type="password" value={token} onChange={(e) => setToken(e.target.value)} required /></label>
        {identity.error ? <p role="alert" className="text-sm text-red-700">{identity.error.message}</p> : null}
        <button className="btn btn-primary" disabled={!token.trim()} type="submit">Sign in</button>
      </form>
    </main>
  );
  return (
    <IdentityContext.Provider value={identity.data}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-1.5 text-xs text-slate-600">
        <span>{identity.data.is_demo ? "Local demonstration · Synthetic finance workspace" : `Shared workspace · ${identity.data.subject} · ${identity.data.role}`}</span>
        {!identity.data.is_demo ? <button type="button" className="font-semibold underline" onClick={() => {
          setAccessToken(""); setAttempt(0); queryClient.clear();
        }}>Sign out</button> : null}
      </div>
      {children}
    </IdentityContext.Provider>
  );
}
