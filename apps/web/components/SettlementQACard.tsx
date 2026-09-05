"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  ExternalLink,
  HelpCircle,
  LoaderCircle,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { askRunQuestion, type QuestionResponse } from "@/lib/api";

interface SettlementQACardProps {
  runId: string;
}

const suggestedPrompts = [
  "Why is CASE_AMB0073 unresolved?",
  "What is our confirmed vs at-risk cash?",
  "What is our Straight-Through Processing (STP) rate?",
  "Which cases had fee variances?",
  "Tell me about CASE_MN0060",
];

export function SettlementQACard({ runId }: SettlementQACardProps) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<QuestionResponse[]>([]);

  const askMutation = useMutation({
    mutationFn: (q: string) => askRunQuestion(runId, q),
    onSuccess: (data) => {
      setHistory((prev) => [data, ...prev]);
      setQuestion("");
    },
  });

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || askMutation.isPending) return;
    askMutation.mutate(trimmed);
  };

  const handlePromptClick = (prompt: string) => {
    setQuestion(prompt);
    askMutation.mutate(prompt);
  };

  return (
    <section className="panel min-w-0" data-testid="settlement-qa-card">
      <div className="panel-header flex flex-wrap items-center justify-between gap-3 border-b border-[#e2e8f0] bg-[#f8fafc] px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border border-[#c7d2fe] bg-[#eef2ff] text-[#4f46e5] shadow-xs">
            <Bot aria-hidden="true" size={20} />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="panel-title m-0 font-bold text-[#0f172a]">Settlement Q&A Agent</h2>
              <span className="inline-flex items-center gap-1 rounded-full border border-[#a7f3d0] bg-[#ecfdf5] px-2.5 py-0.5 text-[0.62rem] font-bold text-[#065f46]">
                <ShieldCheck aria-hidden="true" size={11} /> Grounded Facts
              </span>
            </div>
            <p className="panel-copy m-0 mt-0.5 text-[0.73rem] text-[#64748b]">
              Read-only agent grounded in computed settlement facts and cash invariants.
            </p>
          </div>
        </div>
        <span className="text-[0.65rem] font-semibold text-[#64748b] bg-white border border-[#e2e8f0] rounded-[6px] px-2.5 py-1">
          Non-authoritative · Zero arithmetic hallucinations
        </span>
      </div>

      <div className="p-5 space-y-4">
        {/* Suggested Prompts */}
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-[0.68rem] font-bold uppercase tracking-wider text-[#64748b]">
            <Sparkles aria-hidden="true" size={12} className="text-[#0c44ac]" /> Suggested Queries
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestedPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => handlePromptClick(prompt)}
                disabled={askMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#cbd5e1] bg-white px-3 py-1.5 text-[0.72rem] font-medium text-[#334155] shadow-xs transition-all hover:border-[#0c44ac] hover:bg-[#f0f7ff] hover:text-[#0c44ac] disabled:opacity-50"
              >
                <span>{prompt}</span>
                <ArrowRight aria-hidden="true" size={11} className="opacity-60" />
              </button>
            ))}
          </div>
        </div>

        {/* Query Input */}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about cases, cash confidence buckets, exceptions, or invariants..."
              disabled={askMutation.isPending}
              className="w-full rounded-[6px] border border-[#cbd5e1] bg-white px-3.5 py-2 text-[0.8rem] text-[#0f172a] placeholder-[#94a3b8] focus:border-[#0c44ac] focus:outline-none focus:ring-2 focus:ring-[#0c44ac]/15 disabled:bg-[#f8fafc]"
            />
          </div>
          <button
            type="submit"
            disabled={!question.trim() || askMutation.isPending}
            className="btn btn-primary px-4 py-2 text-[0.78rem]"
          >
            {askMutation.isPending ? (
              <>
                <LoaderCircle aria-hidden="true" size={14} className="animate-spin" />
                Querying...
              </>
            ) : (
              <>
                <Send aria-hidden="true" size={14} />
                Ask Agent
              </>
            )}
          </button>
        </form>

        {/* Error message */}
        {askMutation.isError && (
          <div className="rounded-[6px] border border-[#fecdd3] bg-[#fff1f2] p-3 text-[0.74rem] text-[#9f1239]">
            {askMutation.error.message || "Failed to get an answer from the Q&A agent."}
          </div>
        )}

        {/* Response History */}
        {history.length > 0 && (
          <div className="space-y-4 pt-2">
            {history.map((item, idx) => (
              <article
                key={idx}
                className="rounded-[8px] border border-[#e2e8f0] bg-white shadow-xs overflow-hidden"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#e2e8f0] bg-[#f8fafc] px-4 py-2.5 text-[0.72rem]">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-bold text-[#0f172a] truncate">Q: {item.question}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="rounded bg-[#f1f5f9] border border-[#e2e8f0] px-2 py-0.5 font-mono text-[0.62rem] text-[#475569]">
                      {item.model}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded border border-[#a7f3d0] bg-[#ecfdf5] px-2 py-0.5 text-[0.62rem] font-bold text-[#065f46]">
                      <ShieldCheck aria-hidden="true" size={10} /> Fact Verified
                    </span>
                  </div>
                </div>

                <div className="p-4 text-[0.75rem] leading-relaxed text-[#1e293b] space-y-2">
                  <div className="whitespace-pre-wrap font-sans">{item.answer}</div>

                  {item.cited_case_ids && item.cited_case_ids.length > 0 && (
                    <div className="mt-3 border-t border-[#f1f5f9] pt-2.5">
                      <p className="mb-1.5 text-[0.64rem] font-bold uppercase tracking-wider text-[#64748b]">
                        Cited Case Evidence
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {item.cited_case_ids.map((cid) => (
                          <Link
                            key={cid}
                            href={`/runs/${runId}/cases?search=${encodeURIComponent(cid)}`}
                            className="inline-flex items-center gap-1 rounded-[5px] border border-[#bfdbfe] bg-[#f0f7ff] px-2 py-0.5 font-mono text-[0.67rem] font-bold text-[#0c44ac] hover:border-[#0c44ac] hover:bg-white transition-colors"
                          >
                            <span>{cid}</span>
                            <ExternalLink aria-hidden="true" size={10} className="opacity-70" />
                          </Link>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}

        {history.length === 0 && !askMutation.isPending && (
          <div className="rounded-[6px] border border-dashed border-[#d8e0dc] bg-[#fafbfb] p-6 text-center text-[0.72rem] text-[#717d77]">
            <HelpCircle aria-hidden="true" size={24} className="mx-auto mb-2 text-[#9bb0a5]" />
            <p className="font-medium text-[#404c46]">No questions asked yet for this run.</p>
            <p className="text-[0.67rem] text-[#86928c] mt-1">
              Click a suggested prompt above or type a question to inspect the run&apos;s financial evidence.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
