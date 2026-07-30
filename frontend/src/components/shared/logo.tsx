import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <svg width="26" height="26" viewBox="0 0 26 26" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="13" cy="13" r="12" stroke="var(--teal-600)" strokeWidth="1.4" />
        <path
          d="M13 5.5C13 5.5 8.5 9 8.5 13C8.5 17 13 20.5 13 20.5C13 20.5 17.5 17 17.5 13C17.5 9 13 5.5 13 5.5Z"
          stroke="var(--teal-600)"
          strokeWidth="1.4"
        />
        <circle cx="13" cy="13" r="2.1" fill="var(--brass-600)" />
      </svg>
      <span className="font-display text-[1.15rem] font-semibold tracking-tight text-ink">
        SAIRA
      </span>
    </div>
  );
}
