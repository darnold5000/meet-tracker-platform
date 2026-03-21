"use client";

import type { ScoreRow } from "@/lib/types";
import type { EventKey } from "@/lib/types";

function fmtScore(x: number | null): string {
  return x == null ? "—" : x.toFixed(3);
}
interface ScoreCardProps {
  row: ScoreRow;
  event: EventKey;
  rank: number;
  showPastResults: boolean;
  /** When API `place` is null (e.g. live), ranks by score within the loaded/filtered set. */
  eventRanks?: Partial<Record<EventKey, number>>;
}

function ordinal(p: number): string {
  if (p === 1) return "1st";
  if (p === 2) return "2nd";
  if (p === 3) return "3rd";
  return `${p}th`;
}

function placeLabel(p: number | null): string {
  if (p == null) return "";
  return ordinal(p);
}

/** Show standing: 1st/2nd/3rd or #n (official place from feed, or computed rank for live). */
function formatStanding(p: number | null): string {
  if (p == null) return "";
  if (p <= 3) return placeLabel(p);
  return `#${p}`;
}

export function ScoreCard({ row, event, rank, showPastResults, eventRanks }: ScoreCardProps) {
  const e = row[event];
  const rankBadgeClass = "border border-slate-200 bg-slate-100 text-slate-700";

  const mainOfficialPlace = e.place;
  const mainStanding =
    mainOfficialPlace ?? (e.score != null ? rank : null);

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${rankBadgeClass}`}>
              {rank}
            </span>
            <span className="truncate font-bold text-slate-900">{row.athlete}</span>
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-red-600">{row.gym || "—"}</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {row.session && (
              <span className="max-w-[90px] truncate rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                {row.session}
              </span>
            )}
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
          <div className="text-xs font-semibold text-slate-500">
            {mainStanding != null ? formatStanding(mainStanding) : null}
          </div>
        </div>
      </div>
      <div className="mt-2 flex gap-1 rounded-xl border border-slate-100 bg-slate-50/50 p-1.5">
        {(["vt", "ub", "bb", "fx", "aa"] as const).map((ev) => (
          (() => {
            const officialPlace = row[ev].place;
            const computedPlace =
              row[ev].score != null ? eventRanks?.[ev] ?? null : null;
            const displayPlace = officialPlace ?? computedPlace;
            const medalPillClass =
              showPastResults && officialPlace === 1
                ? "bg-gradient-to-b from-amber-100 to-amber-200 text-amber-900 border border-amber-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]"
                : showPastResults && officialPlace === 2
                ? "bg-gradient-to-b from-slate-100 to-slate-300 text-slate-900 border border-slate-400 shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]"
                : showPastResults && officialPlace === 3
                ? "bg-gradient-to-b from-orange-100 to-orange-300 text-orange-900 border border-orange-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]"
                : "";
            const className =
              medalPillClass ||
              (ev === event
                ? "bg-red-100 text-red-700 border border-red-200"
                : "text-slate-500");

            return (
          <div
            key={ev}
            className={`flex-1 rounded-lg px-1 py-1 text-center text-xs font-bold ${className}`}
          >
            <div className="uppercase">{ev === "aa" ? "AA" : ev}</div>
            <div className="text-slate-700">{fmtScore(row[ev].score)}</div>
            {displayPlace != null && (
              <div className="mt-0.5 text-[10px] font-extrabold">
                {formatStanding(displayPlace)}
              </div>
            )}
          </div>
            );
          })()
        ))}
      </div>
    </div>
  );
}
