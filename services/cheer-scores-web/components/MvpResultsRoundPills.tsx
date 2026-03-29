"use client";

import type { MvpResultsRoundTab } from "@/lib/mvpDedupe";

type Props = {
  value: MvpResultsRoundTab;
  onChange: (t: MvpResultsRoundTab) => void;
  className?: string;
};

export function MvpResultsRoundPills({ value, onChange, className }: Props) {
  const pill = (round: MvpResultsRoundTab, label: string) => {
    const on = value === round;
    return (
      <button
        type="button"
        onClick={() => onChange(round)}
        className={`rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide transition ${
          on
            ? "bg-gradient-to-r from-sky-500 via-cyan-300 to-teal-200 text-slate-900 shadow-sm ring-1 ring-black/10"
            : "border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50"
        }`}
      >
        {label}
      </button>
    );
  };

  return (
    <div
      className={`flex flex-wrap gap-2 ${className ?? ""}`}
      role="group"
      aria-label="Results round"
    >
      {pill("finals", "Finals")}
      {pill("prelims", "Prelims")}
    </div>
  );
}
