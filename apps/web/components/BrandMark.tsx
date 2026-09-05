export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`relative flex shrink-0 items-center justify-center overflow-hidden rounded-[8px] border border-[#1e3a66] bg-gradient-to-br from-[#0c2340] via-[#091b33] to-[#081225] shadow-[0_2px_8px_rgba(12,68,172,0.25)] ${
        compact ? "h-8 w-8" : "h-10 w-10"
      }`}
    >
      <svg
        className="overflow-visible"
        fill="none"
        height={compact ? 18 : 22}
        viewBox="0 0 24 24"
        width={compact ? 18 : 22}
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="razorpayGradient" x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="60%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#1d4ed8" />
          </linearGradient>
        </defs>
        <path
          d="M13.5 2L5.5 13H11.2L9.5 22L18.5 10.5H12.8L13.5 2Z"
          fill="url(#razorpayGradient)"
          stroke="#93c5fd"
          strokeLinejoin="round"
          strokeWidth="0.8"
        />
      </svg>
      <span className="absolute inset-x-0 bottom-0 h-0.5 bg-gradient-to-r from-[#1d4ed8] via-[#38bdf8] to-[#1d4ed8]" />
    </span>
  );
}
