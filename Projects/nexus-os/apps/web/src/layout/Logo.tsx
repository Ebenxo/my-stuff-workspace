export function Logo({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-7 shrink-0" aria-hidden="true">
        <rect width="32" height="32" rx="8" className="fill-accent" />
        <path
          d="M9 23V9l14 14V9"
          fill="none"
          stroke="white"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {collapsed ? null : <span className="text-[15px] font-semibold tracking-[0.18em] text-fg">NEXUS</span>}
    </div>
  );
}
