"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addDays, format } from "date-fns";
import { CalendarClock, CheckCircle2, UserRound, X, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { APIError, submitReview, type ReviewAction } from "@/lib/api";
import { titleCase } from "@/lib/format";

const actions: { value: ReviewAction; label: string; icon: typeof CheckCircle2 }[] = [
  { value: "approve", label: "Approve", icon: CheckCircle2 },
  { value: "reject", label: "Reject", icon: XCircle },
  { value: "defer", label: "Defer", icon: CalendarClock },
  { value: "assign", label: "Assign", icon: UserRound },
];

export function ReviewActionDialog({
  caseId,
  runId,
  open,
  initialAction = "approve",
  canApprove = true,
  approvalBlockReason,
  approvalGuidance,
  onClose,
  onComplete,
}: {
  caseId: string;
  runId: string;
  open: boolean;
  initialAction?: ReviewAction;
  canApprove?: boolean;
  approvalBlockReason?: string;
  approvalGuidance?: string;
  onClose: () => void;
  onComplete?: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const dialogRef = useRef<HTMLDivElement>(null);
  const [action, setAction] = useState<ReviewAction>(initialAction);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [until, setUntil] = useState(format(addDays(new Date(), 3), "yyyy-MM-dd"));
  const [owner, setOwner] = useState("settlement_operations");

  useEffect(() => {
    setAction(initialAction === "approve" && !canApprove ? "assign" : initialAction);
  }, [canApprove, initialAction, open]);
  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    window.setTimeout(() => dialogRef.current?.focus(), 0);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onClose, open]);

  const mutation = useMutation({
    mutationFn: () =>
      submitReview(caseId, action, {
        reason: reason || undefined,
        note: note || undefined,
        ...(action === "defer" ? { until } : {}),
        ...(action === "assign" ? { owner_role: owner } : {}),
      }),
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["cases", runId] }),
        queryClient.invalidateQueries({ queryKey: ["case", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["cash", runId] }),
        queryClient.invalidateQueries({ queryKey: ["audit", runId] }),
      ]);
    },
    onSuccess: (result) => {
      queryClient.setQueryData(["case", caseId], (current: unknown) => {
        if (!current || typeof current !== "object") return current;
        return {
          ...current,
          case_state: result.new_state,
          human_reviewed: true,
        };
      });
      queryClient.setQueryData(["cases", runId], (current: unknown) => {
        if (!current || typeof current !== "object" || !("items" in current)) return current;
        const page = current as { items: Array<Record<string, unknown>> };
        return {
          ...page,
          items: page.items.map((item) =>
            item.case_id === caseId
              ? { ...item, case_state: result.new_state, human_reviewed: true }
              : item,
          ),
        };
      });
      onComplete?.(`${titleCase(result.action)} recorded. Case is ${titleCase(result.new_state)}.`);
      onClose();
    },
  });

  if (!open) return null;
  const error = mutation.error;

  return (
    <div
      aria-label="Review case"
      aria-labelledby="review-dialog-title"
      aria-modal="true"
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[#0b1712]/60 p-4 backdrop-blur-[2px]"
      data-testid="review-dialog"
      role="dialog"
    >
      <div
        className="w-full max-w-[540px] overflow-hidden rounded-[8px] border border-[#cbd5d0] bg-white shadow-[0_24px_70px_rgba(10,25,19,0.28)] outline-none"
        ref={dialogRef}
        tabIndex={-1}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#dbe3df] bg-[#fbfcfb] px-5 py-4">
          <div>
            <p className="eyebrow">Controlled action</p>
            <h2 className="m-0 text-base font-bold" id="review-dialog-title">Record human decision</h2>
            <p className="mb-0 mt-1 font-mono text-[0.69rem] text-[#6e7a75]">{caseId}</p>
            <p className="mb-0 mt-2 inline-flex items-center gap-1.5 rounded-full bg-[#edf1ef] px-2 py-1 text-[0.62rem] font-bold text-[#637169]">
              <UserRound aria-hidden="true" size={11} /> demo.finance.operator
            </p>
          </div>
          <button aria-label="Close review dialog" className="btn btn-ghost btn-icon" onClick={onClose}>
            <X aria-hidden="true" size={18} />
          </button>
        </div>
        <form
          className="space-y-4 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (action === "approve" && !canApprove) return;
            mutation.mutate();
          }}
        >
          <div className="grid grid-cols-4 overflow-hidden rounded-[7px] border border-[#cbd5d0] bg-[#f8faf9] p-1">
            {actions.map(({ value, label, icon: Icon }) => {
              const actionDisabled = value === "approve" && !canApprove;
              return (
                <button
                  aria-label={label}
                  aria-pressed={action === value}
                  className={`flex min-h-10 items-center justify-center gap-1.5 rounded-[5px] px-2 text-[0.7rem] font-bold ${
                    actionDisabled
                      ? "cursor-not-allowed text-[#9aa39f] opacity-70"
                      : action === value
                        ? "bg-white text-[#245fda] shadow-[0_1px_4px_rgba(23,38,32,0.12)]"
                        : "text-[#5f6d66] hover:bg-white/70 hover:text-[#2c3933]"
                  }`}
                  disabled={actionDisabled}
                  key={value}
                  onClick={() => {
                    mutation.reset();
                    setAction(value);
                  }}
                  title={actionDisabled ? approvalBlockReason : undefined}
                  type="button"
                >
                  <Icon aria-hidden="true" size={14} />
                  <span className="hidden sm:inline">{label}</span>
                </button>
              );
            })}
          </div>

          {action === "defer" ? (
            <div className="field">
              <label htmlFor="review-until">Defer until</label>
              <input
                className="input"
                id="review-until"
                min={format(new Date(), "yyyy-MM-dd")}
                onChange={(event) => setUntil(event.target.value)}
                required
                type="date"
                value={until}
              />
            </div>
          ) : null}

          {action === "assign" ? (
            <div className="field">
              <label htmlFor="review-owner">Owner role</label>
              <input
                className="input"
                id="review-owner"
                onChange={(event) => setOwner(event.target.value)}
                required
                value={owner}
              />
            </div>
          ) : null}

          <div className="field">
            <label htmlFor="review-reason">Reason {action === "reject" ? "(required)" : ""}</label>
            <input
              className="input"
              id="review-reason"
              onChange={(event) => setReason(event.target.value)}
              placeholder="Decision rationale"
              required={action === "reject"}
              value={reason}
            />
          </div>
          <div className="field">
            <label htmlFor="review-note">Internal note</label>
            <textarea
              className="textarea"
              id="review-note"
              onChange={(event) => setNote(event.target.value)}
              placeholder="Optional context for the audit trail"
              value={note}
            />
          </div>

          {action === "approve" && canApprove ? (
            <p className="rounded-[5px] border border-[#efd49a] bg-[#fff8e8] px-3 py-2 text-[0.72rem] leading-5 text-[#78501a]">
              {approvalGuidance ??
                "Approval reruns deterministic invariants. A human decision cannot override a failed financial check."}
            </p>
          ) : null}

          {error ? (
            <p className="rounded-[5px] border border-[#edb9b6] bg-[#fdeceb] px-3 py-2 text-[0.72rem] leading-5 text-[#9d302c]">
              {error instanceof APIError ? error.message : "The decision could not be recorded."}
            </p>
          ) : null}

          <div className="flex justify-end gap-2 border-t border-[#e1e7e4] pt-4">
            <button className="btn btn-secondary" onClick={onClose} type="button">
              Cancel
            </button>
            <button
              className={action === "reject" ? "btn btn-danger" : "btn btn-primary"}
              data-testid="confirm-review-action"
              disabled={mutation.isPending || (action === "approve" && !canApprove)}
              type="submit"
            >
              {mutation.isPending ? "Recording..." : `Confirm ${titleCase(action)}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
