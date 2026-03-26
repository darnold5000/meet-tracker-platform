"use client";

import type { MvpResultRow } from "@/lib/mvpTypes";

function rankOrdinal(n: number | null): string {
  if (n == null) return "";
  const j = n % 10;
  const k = n % 100;
  if (j === 1 && k !== 11) return `${n}st`;
  if (j === 2 && k !== 12) return `${n}nd`;
  if (j === 3 && k !== 13) return `${n}rd`;
  return `${n}th`;
}

function fmt(n: number): string {
  return n.toFixed(2);
}

export function MvpResultScoreBreakdown({
  r,
  showRankOrdinal = true,
  scoreSizeClass = "text-lg",
}: {
  r: MvpResultRow;
  showRankOrdinal?: boolean;
  scoreSizeClass?: string;
}) {
  const hasRS = r.raw_score != null;
  const hasPS = r.performance_score != null;
  const hasDED = r.deductions != null;
  const showDetail = hasRS || hasPS || hasDED;

  return (
    <div className="shrink-0 text-right">
      <div className={`font-bold tabular-nums text-[var(--text)] ${scoreSizeClass}`}>
        <span className="mr-1 text-[9px] font-semibold uppercase tracking-wide text-[var(--muted)]">
          ES
        </span>
        {fmt(r.final_score)}
      </div>
      {showRankOrdinal && r.rank != null && (
        <div className="text-[10px] text-[var(--muted)]">{rankOrdinal(r.rank)}</div>
      )}
      {showDetail && (
        <div className="mt-1 space-y-0.5 text-[10px] tabular-nums text-[var(--muted)]">
          {hasRS && (
            <div>
              <span className="font-semibold text-slate-600">RS</span> {fmt(r.raw_score!)}
            </div>
          )}
          {hasPS && (
            <div>
              <span className="font-semibold text-slate-600">PS</span> {fmt(r.performance_score!)}
            </div>
          )}
          {hasDED && (
            <div>
              <span className="font-semibold text-slate-600">DED</span> −{fmt(r.deductions!)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
