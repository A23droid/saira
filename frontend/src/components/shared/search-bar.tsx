"use client";

import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

export function SearchBar({
  value,
  onChange,
  placeholder = "Search papers, authors, topics…",
  className,
  onSubmit,
  isLoading,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  onSubmit?: () => void;
  isLoading?: boolean;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit?.();
      }}
      className={cn(
        "flex h-13 items-center gap-3 rounded-full border border-line bg-surface px-5 py-3 shadow-sm transition-shadow focus-within:shadow-md focus-within:border-teal-500",
        className
      )}
    >
      <Search className="h-4.5 w-4.5 shrink-0 text-ink-faint" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
      />
      {onSubmit && (
        <button
          type="submit"
          disabled={isLoading || !value.trim()}
          className="shrink-0 rounded-full bg-teal-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-teal-700 disabled:opacity-50"
        >
          {isLoading ? "Searching..." : "Search"}
        </button>
      )}
    </form>
  );
}
