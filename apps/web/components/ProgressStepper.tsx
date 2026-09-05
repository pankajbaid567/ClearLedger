import { Check, LoaderCircle } from "lucide-react";

export function ProgressStepper({
  stages,
  activeIndex,
}: {
  stages: string[];
  activeIndex: number;
}) {
  return (
    <ol aria-live="polite" className="grid list-none grid-cols-2 gap-x-3 gap-y-4 p-0 sm:grid-cols-4 lg:grid-cols-8">
      {stages.map((stage, index) => {
        const complete = index < activeIndex || activeIndex >= stages.length;
        const active = index === activeIndex && activeIndex < stages.length;
        return (
          <li aria-current={active ? "step" : undefined} className="relative min-w-0" key={stage}>
            <div className="flex items-center gap-2">
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[0.67rem] font-bold ${
                  complete
                    ? "border-[#059669] bg-[#059669] text-white"
                    : active
                      ? "border-[#0c44ac] bg-[#eff6ff] text-[#0c44ac] shadow-[0_0_0_3px_rgba(12,68,172,0.12)]"
                      : "border-[#cbd5e1] bg-white text-[#64748b]"
                }`}
              >
                {complete ? (
                  <Check aria-hidden="true" size={13} strokeWidth={2.5} />
                ) : active ? (
                  <LoaderCircle aria-hidden="true" className="animate-spin" size={13} />
                ) : (
                  index + 1
                )}
              </span>
              <span className={`min-w-0 text-[0.67rem] leading-4 ${active ? "text-[#0c44ac] font-bold" : complete ? "text-[#0f172a] font-semibold" : "text-[#64748b] font-medium"}`}>
                {stage}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
