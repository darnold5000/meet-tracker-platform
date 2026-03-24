"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { mvpResults, mvpTimeline } from "@/lib/mvpApi";
import type { MvpResultRow, MvpTimelineItem, MvpTimelineResponse } from "@/lib/mvpTypes";
import { pushMvpRecent } from "@/lib/mvpRecents";

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function statusTone(status: string): { label: string; className: string } {
  const s = status.toLowerCase();
  if (s === "live") return { label: "LIVE", className: "bg-red-500 text-white" };
  if (s === "completed") return { label: "Done", className: "bg-emerald-600 text-white" };
  return { label: "Upcoming", className: "bg-slate-200 text-slate-800" };
}

function medalForRank(rank: number | null): string {
  if (rank === 1) return "🥇 ";
  if (rank === 2) return "🥈 ";
  if (rank === 3) return "🥉 ";
  return "";
}

export function MvpMeetPage({ meetKey }: { meetKey: string }) {
  const [tab, setTab] = useState<"timeline" | "results">("timeline");
  const [sessionId, setSessionId] = useState<number | "">("");
  const [timeline, setTimeline] = useState<MvpTimelineResponse | null>(null);
  const [results, setResults] = useState<MvpResultRow[]>([]);
  const [loadingT, setLoadingT] = useState(true);
  const [loadingR, setLoadingR] = useState(false);
  const [errT, setErrT] = useState<string | null>(null);
  const [errR, setErrR] = useState<string | null>(null);

  const sid = sessionId === "" ? null : sessionId;

  useEffect(() => {
    let cancelled = false;
    setErrT(null);
    setLoadingT(true);
    (async () => {
      try {
        const tl = await mvpTimeline(meetKey, sid);
        if (cancelled) return;
        setTimeline(tl);
        pushMvpRecent({ kind: "meet", meetKey: tl.meet_key, label: tl.meet.name });
      } catch (e) {
        if (cancelled) return;
        setTimeline(null);
        setErrT(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoadingT(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [meetKey, sid]);

  useEffect(() => {
    if (tab !== "results") return;
    let cancelled = false;
    setErrR(null);
    setLoadingR(true);
    (async () => {
      try {
        const res = await mvpResults(meetKey, sid);
        if (cancelled) return;
        setResults(res.results);
      } catch (e) {
        if (cancelled) return;
        setResults([]);
        setErrR(e instanceof Error ? e.message : "Failed to load results");
      } finally {
        if (!cancelled) setLoadingR(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, meetKey, sid]);

  const sessions = timeline?.sessions ?? [];
  const filteredItems: MvpTimelineItem[] = useMemo(() => timeline?.items ?? [], [timeline]);
  const liveNow = filteredItems.find((i) => !i.is_break && i.status.toLowerCase() === "live");

  const loading = tab === "timeline" ? loadingT : loadingR;
  const err = tab === "timeline" ? errT : errR;

  return (
    <div className="mx-auto max-w-lg px-4 pb-16 pt-6">
      <Link href="/" className="mb-4 inline-block text-sm font-medium text-[var(--brand)]">
        ← Search
      </Link>

      {timeline && (
        <header className="mb-4 rounded-2xl bg-[var(--brand)] px-4 py-4 text-white shadow-lg">
          <h1 className="text-lg font-bold leading-tight">{timeline.meet.name}</h1>
          <p className="mt-1 text-sm opacity-90">
            {[timeline.meet.location, timeline.meet.start_date].filter(Boolean).join(" · ")}
          </p>
          {liveNow && (
            <p className="mt-3 rounded-lg bg-white/15 px-3 py-2 text-sm font-semibold">
              Live now · {liveNow.team_name} {liveNow.team_level ? `(${liveNow.team_level})` : ""}
            </p>
          )}
        </header>
      )}

      {!timeline && loadingT && <p className="text-sm text-[var(--muted)]">Loading meet…</p>}
      {errT && !timeline && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{errT}</p>}

      {sessions.length > 0 && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Session
          </label>
          <select
            value={sessionId === "" ? "" : String(sessionId)}
            onChange={(e) => {
              const v = e.target.value;
              setSessionId(v === "" ? "" : Number(v));
            }}
            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm"
          >
            <option value="">All sessions</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="mb-4 flex gap-2 rounded-xl bg-slate-200/80 p-1">
        <button
          type="button"
          onClick={() => setTab("timeline")}
          className={`flex-1 rounded-lg py-2 text-sm font-semibold ${
            tab === "timeline" ? "bg-white text-[var(--brand)] shadow" : "text-[var(--muted)]"
          }`}
        >
          Timeline
        </button>
        <button
          type="button"
          onClick={() => setTab("results")}
          className={`flex-1 rounded-lg py-2 text-sm font-semibold ${
            tab === "results" ? "bg-white text-[var(--brand)] shadow" : "text-[var(--muted)]"
          }`}
        >
          Results
        </button>
      </div>

      {loading && <p className="text-sm text-[var(--muted)]">Loading…</p>}
      {err && timeline && <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{err}</p>}

      {!loading && tab === "timeline" && timeline && (
        <ol className="space-y-2">
          {filteredItems.map((row) => {
            if (row.is_break) {
              return (
                <li
                  key={row.performance_id}
                  className="flex items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-3 py-3 text-sm text-[var(--muted)]"
                >
                  <span className="w-14 shrink-0 font-mono text-xs">{formatTime(row.scheduled_time)}</span>
                  <span>{row.break_label || "Break"}</span>
                </li>
              );
            }
            const st = statusTone(row.status);
            return (
              <li
                key={row.performance_id}
                className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm"
              >
                <div className="w-14 shrink-0 font-mono text-xs text-[var(--muted)]">
                  {formatTime(row.scheduled_time)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-[var(--text)]">{row.team_name}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${st.className}`}>
                      {st.label}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-[var(--muted)]">
                    {[row.team_level, row.team_division, row.round].filter(Boolean).join(" · ")}
                  </div>
                  <div className="mt-1 text-[10px] uppercase tracking-wide text-slate-400">{row.session_name}</div>
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {!loading && tab === "results" && (
        <ol className="space-y-2">
          {results.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No scored routines for this filter yet.</p>
          ) : (
            results.map((r, idx) => (
              <li
                key={`${r.team_name}-${idx}`}
                className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-[var(--text)]">
                    {medalForRank(r.rank)}
                    {r.team_name}
                  </div>
                  <div className="text-xs text-[var(--muted)]">
                    {[r.team_level, r.team_division, r.session_name].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-lg font-bold tabular-nums text-[var(--brand)]">{r.final_score.toFixed(2)}</div>
                  {r.deductions != null && (
                    <div className="text-[10px] text-[var(--muted)]">−{r.deductions.toFixed(2)} ded.</div>
                  )}
                </div>
              </li>
            ))
          )}
        </ol>
      )}
    </div>
  );
}
