"use client";

import type { ScoreRow } from "@/lib/types";
import type { EventKey } from "@/lib/types";

function fmtScore(x: number | null): string {
  return x == null ? "—" : x.toFixed(3);
}
function fmtPlace(p: number | null): string {
  return p == null ? "" : `#${p}`;
}

interface ScoreCardProps {
  row: ScoreRow;
  event: EventKey;
  rank: number;
}

export function ScoreCard({ row, event, rank }: ScoreCardProps) {
  const e = row[event];
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-600 text-xs font-bold text-white">
              {rank}
            </span>
            <span className="truncate font-bold text-slate-900">{row.athlete}</span>
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-red-600">{row.gym || "—"}</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
              {row.level || "—"}
            </span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
              {row.division || "—"}
            </span>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-bold text-slate-900">{fmtScore(e.score)}</div>
          <div className="text-xs font-semibold text-slate-500">{fmtPlace(e.place)}</div>
        </div>
      </div>
      <div className="mt-2 flex gap-1 rounded-xl border border-slate-100 bg-slate-50/50 p-1.5">
        {(["vt", "ub", "bb", "fx", "aa"] as const).map((ev) => (
          <div
            key={ev}
            className={`flex-1 rounded-lg px-1 py-1 text-center text-xs font-bold ${
              ev === event
                ? "bg-red-100 text-red-700 border border-red-200"
                : "text-slate-500"
            }`}
          >
            <div className="uppercase">{ev === "aa" ? "AA" : ev}</div>
            <div className="text-slate-700">{fmtScore(row[ev].score)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
