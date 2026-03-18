"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchScores } from "@/lib/api";
import type { ScoreRow, ScoresResponse, EventKey } from "@/lib/types";
import { EVENTS } from "@/lib/types";
import { ScoreCard } from "./ScoreCard";

const DEFAULT_MEET_KEY = process.env.NEXT_PUBLIC_DEFAULT_MEET_KEY ?? "MSO-36478";
const REFRESH_INTERVAL_MS = 20_000;

function sortByEvent(rows: ScoreRow[], event: EventKey): ScoreRow[] {
  return [...rows].sort((a, b) => {
    const sa = a[event].score;
    const sb = b[event].score;
    if (sa == null && sb == null) return a.athlete.localeCompare(b.athlete);
    if (sa == null) return 1;
    if (sb == null) return -1;
    return sb - sa;
  });
}

interface MeetViewProps {
  meetKey?: string;
  meetName?: string;
}

export function MeetView({ meetKey = DEFAULT_MEET_KEY, meetName }: MeetViewProps) {
  const [data, setData] = useState<ScoresResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState("All");
  const [division, setDivision] = useState("All");
  const [q, setQ] = useState("");
  const [event, setEvent] = useState<EventKey>("aa");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchScores(meetKey, { level, division, q, limit: 500 });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load scores");
    } finally {
      setLoading(false);
    }
  }, [meetKey, level, division, q]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(load, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  const levels = data ? ["All", ...new Set(data.rows.map((r) => r.level).filter(Boolean))] : ["All"];
  const divisions = data ? ["All", ...new Set(data.rows.map((r) => r.division).filter(Boolean))] : ["All"];
  const sorted = data ? sortByEvent(data.rows, event) : [];

  return (
    <div className="mx-auto max-w-lg px-4 pb-12 pt-6">
      <header className="rounded-2xl bg-[var(--brand)] px-4 py-3 text-white shadow-lg">
        <div className="flex items-center justify-between">
          <span className="font-extrabold tracking-wide">GYM SCORES</span>
          <span className="text-sm font-bold opacity-90">LIVE</span>
        </div>
        {meetName && <p className="mt-1 text-sm font-semibold opacity-90">{meetName}</p>}
        <p className="text-xs opacity-75">Meet: {meetKey}</p>
      </header>

      <div className="mt-4 rounded-xl bg-white/20 p-3">
        <input
          type="search"
          placeholder="Search athletes or gyms…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full rounded-full border border-white/30 bg-white/10 px-4 py-2.5 text-sm placeholder:text-white/70 focus:outline-none focus:ring-2 focus:ring-red-400"
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-400"
          >
            {levels.map((l) => (
              <option key={l} value={l}>
                {l || "All"}
              </option>
            ))}
          </select>
          <select
            value={division}
            onChange={(e) => setDivision(e.target.value)}
            className="rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-red-400"
          >
            {divisions.map((d) => (
              <option key={d} value={d}>
                {d || "All"}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded"
            />
            Auto (20s)
          </label>
        </div>
      </div>

      <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
        {EVENTS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setEvent(key)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-bold ${
              event === key
                ? "bg-red-600 text-white shadow-md"
                : "bg-white/80 text-slate-700 border border-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-4 rounded-xl bg-red-100 p-4 text-red-800">
          {error}. Ensure the FastAPI backend is running and NEXT_PUBLIC_API_URL is correct.
        </div>
      )}

      {loading && !data && (
        <div className="mt-8 text-center text-slate-500">Loading…</div>
      )}

      {data && (
        <>
          <p className="mt-2 text-sm font-semibold text-slate-500">{data.count} athletes</p>
          <ul className="mt-3 space-y-3">
            {sorted.map((row, i) => (
              <li key={`${row.athlete}-${row.level}-${row.division}`}>
                <ScoreCard row={row} event={event} rank={i + 1} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
