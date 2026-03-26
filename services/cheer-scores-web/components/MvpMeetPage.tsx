"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { MVP_DEFAULT_MEET_KEY, MVP_DEFAULT_MEET_LABEL } from "@/lib/mvpDefaults";
import {
  dedupeMvpResultRows,
  dedupeMvpTimelineItems,
  filterMvpResultsByRoundTab,
  mvpResultIsFinalsRound,
  type MvpResultsRoundTab,
} from "@/lib/mvpDedupe";
import { mvpResults, mvpTimeline } from "@/lib/mvpApi";
import {
  formatMvpMeetDateRangeReadable,
  getMvpMeetScheduleStatus,
  mvpMeetHeaderNameLine,
  mvpMeetPickerLabel,
  mvpMeetShowsTimelineTab,
  mvpMeetSummaryToHit,
} from "@/lib/mvpMeetDisplay";
import type { MvpResultRow, MvpTimelineItem, MvpTimelineResponse } from "@/lib/mvpTypes";
import { pushMvpRecent } from "@/lib/mvpRecents";
import { MvpResultScoreBreakdown } from "@/components/MvpResultScoreBreakdown";

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function statusTone(
  status: string,
  finalScore: number | null | undefined
): { label: string; className: string } {
  const s = status.toLowerCase();
  if (s === "live") return { label: "LIVE", className: "bg-[var(--accent)] text-[var(--accent-foreground)]" };
  if (s === "completed" || s === "final" || finalScore != null) {
    return { label: "Done", className: "bg-[var(--brand-bright)] text-white" };
  }
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
  const [resultsRoundTab, setResultsRoundTab] = useState<MvpResultsRoundTab>("finals");

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
        pushMvpRecent({
          kind: "meet",
          meetKey: tl.meet_key,
          label: mvpMeetPickerLabel(mvpMeetSummaryToHit(tl.meet)),
        });
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
    setResultsRoundTab("finals");
    setResults([]);
  }, [meetKey]);

  useEffect(() => {
    if (!timeline?.meet) return;
    if (!mvpMeetShowsTimelineTab(timeline.meet)) setTab("results");
  }, [timeline]);

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

  useEffect(() => {
    if (results.length === 0) return;
    if (!results.some(mvpResultIsFinalsRound)) setResultsRoundTab("prelims");
  }, [meetKey, results]);

  const sessions = timeline?.sessions ?? [];
  const filteredItems: MvpTimelineItem[] = useMemo(() => timeline?.items ?? [], [timeline]);
  const displayTimelineItems = useMemo(
    () => dedupeMvpTimelineItems(filteredItems),
    [filteredItems]
  );
  const resultsFilteredByRound = useMemo(
    () => filterMvpResultsByRoundTab(results, resultsRoundTab),
    [results, resultsRoundTab]
  );
  const displayResultRows = useMemo(
    () => dedupeMvpResultRows(resultsFilteredByRound),
    [resultsFilteredByRound]
  );
  const headerNameLine = timeline
    ? mvpMeetHeaderNameLine(timeline.meet, meetKey, MVP_DEFAULT_MEET_KEY, MVP_DEFAULT_MEET_LABEL)
    : "";
  const scheduleStatus = getMvpMeetScheduleStatus(timeline?.meet ?? null);
  const headerLocationLine = timeline ? (timeline.meet.location ?? "").trim() || null : null;
  const headerDateRangeLine = timeline ? formatMvpMeetDateRangeReadable(timeline.meet) : null;
  const showTimelineTab = mvpMeetShowsTimelineTab(timeline?.meet);

  const loading = tab === "timeline" ? loadingT : loadingR;
  const err = tab === "timeline" ? errT : errR;

  return (
    <div className="mx-auto max-w-lg px-4 pb-16 pt-6">
      <Link href="/" className="mb-4 inline-block text-sm font-medium text-[var(--brand-bright)]">
        ← Home
      </Link>

      {timeline && headerNameLine && (
        <header className="mb-4 rounded-2xl bg-gradient-to-br from-[var(--brand)] via-[#003d52] to-[var(--brand-bright)] px-4 py-4 text-white shadow-lg">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h1 className="text-lg font-bold uppercase leading-tight tracking-wide">{headerNameLine}</h1>
            </div>
            {scheduleStatus.tone !== "past" && (
              <span
                className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${
                  scheduleStatus.tone === "live"
                    ? "bg-red-500 text-white"
                    : "bg-amber-400 text-black"
                }`}
              >
                {scheduleStatus.label}
              </span>
            )}
          </div>
          {(headerLocationLine || headerDateRangeLine) && (
            <div className="mt-3 flex items-start justify-between gap-4 border-t border-white/20 pt-3 text-sm leading-snug">
              <div className="min-w-0 flex-1 text-white/90">
                {headerLocationLine ? <p>{headerLocationLine}</p> : null}
              </div>
              {headerDateRangeLine && (
                <p className="max-w-[58%] shrink-0 text-right font-medium text-white">{headerDateRangeLine}</p>
              )}
            </div>
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

      <div className="mb-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-100/90 shadow-sm ring-1 ring-slate-200/60">
        {showTimelineTab ? (
          <div className="flex gap-1 p-1">
            <button
              type="button"
              onClick={() => setTab("timeline")}
              className={`flex-1 rounded-full py-2 text-sm font-bold uppercase tracking-wide ${
                tab === "timeline"
                  ? "bg-[var(--accent)] text-[var(--accent-foreground)] shadow-sm"
                  : "text-[var(--muted)]"
              }`}
            >
              Timeline
            </button>
            <button
              type="button"
              onClick={() => setTab("results")}
              className={`flex-1 rounded-full py-2 text-sm font-bold uppercase tracking-wide ${
                tab === "results"
                  ? "bg-[var(--accent)] text-[var(--accent-foreground)] shadow-sm"
                  : "text-[var(--muted)]"
              }`}
            >
              Results
            </button>
          </div>
        ) : (
          <div
            className="bg-[var(--accent)] px-3 py-2 text-center text-sm font-bold uppercase tracking-wide text-[var(--accent-foreground)]"
            role="status"
          >
            Results
          </div>
        )}
        {tab === "results" && (
          <div className="flex gap-1 border-t border-slate-200/80 bg-slate-50/95 p-1">
            <button
              type="button"
              onClick={() => setResultsRoundTab("finals")}
              className={`flex-1 rounded-full py-1.5 text-xs font-bold uppercase tracking-wide ${
                resultsRoundTab === "finals"
                  ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200"
                  : "text-[var(--muted)]"
              }`}
            >
              Finals
            </button>
            <button
              type="button"
              onClick={() => setResultsRoundTab("prelims")}
              className={`flex-1 rounded-full py-1.5 text-xs font-bold uppercase tracking-wide ${
                resultsRoundTab === "prelims"
                  ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200"
                  : "text-[var(--muted)]"
              }`}
            >
              Prelims
            </button>
          </div>
        )}
      </div>

      {loading && <p className="text-sm text-[var(--muted)]">Loading…</p>}
      {err && timeline && <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{err}</p>}

      {!loading && tab === "timeline" && timeline && (
        <ol className="space-y-2">
          {displayTimelineItems.map((row) => {
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
            const st = statusTone(row.status, row.final_score);
            const sessionLine = row.session_name?.trim() || "";
            const extraMeta = [row.team_level, row.team_division, row.round].filter(Boolean).filter(
              (bit) => !sessionLine.toLowerCase().includes(String(bit).toLowerCase())
            );
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
                  {row.team_gym_name && (
                    <div className="mt-0.5 text-xs font-medium text-[var(--gym)]">{row.team_gym_name}</div>
                  )}
                  {sessionLine && (
                    <div className="mt-0.5 text-xs text-[var(--muted)]">{sessionLine}</div>
                  )}
                  {extraMeta.length > 0 && (
                    <div className="mt-0.5 text-[10px] text-slate-500">{extraMeta.join(" · ")}</div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {!loading && tab === "results" && (
        <ol className="space-y-2">
          {displayResultRows.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No scored routines for this filter yet.</p>
          ) : (
            displayResultRows.map((r, idx) => {
              const sessionLine = r.session_name?.trim() || "";
              const extras = [r.team_level, r.team_division].filter(Boolean).filter(
                (bit) => !sessionLine.toLowerCase().includes(String(bit).toLowerCase())
              );
              const line = [sessionLine, ...extras].filter(Boolean).join(" · ");
              return (
                <li
                  key={`${r.team_name}-${r.session_id}-${idx}`}
                  className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-[var(--text)]">
                      {medalForRank(r.rank)}
                      {r.team_name}
                    </div>
                    {r.team_gym_name && (
                      <div className="text-xs font-medium text-[var(--gym)]">{r.team_gym_name}</div>
                    )}
                    {line && <div className="text-xs text-[var(--muted)]">{line}</div>}
                  </div>
                  <MvpResultScoreBreakdown r={r} showRankOrdinal={false} />
                </li>
              );
            })
          )}
        </ol>
      )}
    </div>
  );
}
