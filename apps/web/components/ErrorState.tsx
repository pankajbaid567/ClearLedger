import { RefreshCw, TriangleAlert } from "lucide-react";

export function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <section className="panel flex min-h-64 flex-col items-center justify-center px-6 py-10 text-center" role="alert">
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#fff0ef] text-[#b63834]">
        <TriangleAlert aria-hidden="true" size={20} />
      </span>
      <h1 className="mb-0 mt-4 text-[1rem] font-bold text-[#2c3933]">{title}</h1>
      <p className="mb-0 mt-2 max-w-md text-[0.74rem] leading-5 text-[#6e7c75]">{message}</p>
      {onRetry ? (
        <button className="btn btn-secondary mt-5" onClick={onRetry} type="button">
          <RefreshCw aria-hidden="true" size={14} /> Retry
        </button>
      ) : null}
    </section>
  );
}
