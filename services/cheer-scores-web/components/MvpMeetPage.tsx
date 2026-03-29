"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MVP_DEFAULT_MEET_KEY, MVP_DEFAULT_MEET_LABEL } from "@/lib/mvpDefaults";
import {
  dedupeMvpResultRows,
  dedupeMvpTimelineItems,
  filterMvpResultsByRoundTab,
  mvpResultRowMetaExtras,
  mvpResultsRoundAvailability,
  mvpSuggestResultsRoundTab,
  type MvpResultsRoundTab,
} from "@/lib/mvpDedupe";
import { mvpResults, mvpSearch, mvpTimeline } from "@/lib/mvpApi";
import {
  formatMvpMeetDateRangeReadable,
  formatMvpMeetStartsAtReadable,
  getMvpMeetScheduleStatus,
  mvpCoalesceMeetLocation,
  mvpMeetHeaderNameLine,
  mvpMeetPickerLabel,
  mvpMeetShowsTimelineTab,
  mvpMeetSummaryToHit,
  mvpResultRowScheduleCaption,
  mvpTimelineWhenDisplay,
} from "@/lib/mvpMeetDisplay";
import type { MvpMeetHit, MvpResultRow, MvpTimelineItem, MvpTimelineResponse } from "@/lib/mvpTypes";
import { pushMvpRecent } from "@/lib/mvpRecents";
import { MvpResultScoreBreakdown } from "@/components/MvpResultScoreBreakdown";
import { MvpInstallHintBanner } from "@/components/MvpPwaInstallProvider";
import { MvpMeetResultsScheduleTabs } from "@/components/MvpMeetResultsScheduleTabs";
import { MvpResultsRoundPills } from "@/components/MvpResultsRoundPills";
import { varsityOfficialScheduleUrlForMeetKey } from "@/lib/mvpVarsityLinks";
import { openTallyFeedback, TALLY_FEEDBACK_FORM_ID } from "@/lib/feedback";
import { useMvpLiveAutoRefresh } from "@/lib/useMvpLiveAutoRefresh";

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

function mvpFeedbackHelpfulDismissStorageKey(key: string) {
  return `cheer-mvp-feedback-helpful-dismissed-${key}`;
}

export function MvpMeetPage({ meetKey }: { meetKey: string }) {
  const resultsRoundTabInitializedRef = useRef(false);
  const [tab, setTab] = useState<"timeline" | "results">("results");
  const [sessionId, setSessionId] = useState<number | "">("");
  const [timeline, setTimeline] = useState<MvpTimelineResponse | null>(null);
  const [results, setResults] = useState<MvpResultRow[]>([]);
  const [loadingT, setLoadingT] = useState(true);
  const [loadingR, setLoadingR] = useState(false);
  const [errT, setErrT] = useState<string | null>(null);
  const [errR, setErrR] = useState<string | null>(null);
  const [resultsRoundTab, setResultsRoundTab] = useState<MvpResultsRoundTab>("finals");
  const [searchMeetHit, setSearchMeetHit] = useState<MvpMeetHit | null>(null);
  const [contextualFeedbackDismissed, setContextualFeedbackDismissed] = useState(false);
  const [autoRefreshLiveScores, setAutoRefreshLiveScores] = useState(true);

  const sid = sessionId === "" ? null : sessionId;
  const meetKeyRef = useRef(meetKey);
  meetKeyRef.current = meetKey;
  const sidRef = useRef(sid);
  sidRef.current = sid;

  useEffect(() => {
    let cancelled = false;
    setSearchMeetHit(null);
    (async () => {
      try {
        const res = await mvpSearch("");
        if (cancelled) return;
        setSearchMeetHit(res.meets.find((m) => m.meet_key === meetKey) ?? null);
      } catch {
        if (!cancelled) setSearchMeetHit(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [meetKey]);

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
    resultsRoundTabInitializedRef.current = false;
    setResultsRoundTab("finals");
    setResults([]);
    setTab("results");
  }, [meetKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const k = mvpFeedbackHelpfulDismissStorageKey(meetKey);
      setContextualFeedbackDismissed(window.localStorage.getItem(k) === "1");
    } catch {
      setContextualFeedbackDismissed(false);
    }
  }, [meetKey]);

  const dismissContextualFeedbackHelpful = useCallback(() => {
    try {
      window.localStorage.setItem(mvpFeedbackHelpfulDismissStorageKey(meetKey), "1");
    } catch {
      /* ignore */
    }
    setContextualFeedbackDismissed(true);
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

  const { hasFinals: hasFinalsRoundScores, hasPrelims: hasPrelimsRoundScores } = useMemo(
    () => mvpResultsRoundAvailability(results),
    [results]
  );
  const showResultsRoundPills = hasFinalsRoundScores && hasPrelimsRoundScores;

  useEffect(() => {
    if (results.length > 0 && !resultsRoundTabInitializedRef.current) {
      setResultsRoundTab(mvpSuggestResultsRoundTab(results));
      resultsRoundTabInitializedRef.current = true;
    }
  }, [results]);

  useEffect(() => {
    if (!hasFinalsRoundScores && hasPrelimsRoundScores && resultsRoundTab === "finals") {
      setResultsRoundTab("prelims");
    }
    if (hasFinalsRoundScores && !hasPrelimsRoundScores && resultsRoundTab === "prelims") {
      setResultsRoundTab("finals");
    }
  }, [hasFinalsRoundScores, hasPrelimsRoundScores, resultsRoundTab]);

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
  const meetStartsReadable = formatMvpMeetStartsAtReadable(timeline?.meet ?? null);
  const headerLocationLine = timeline
    ? mvpCoalesceMeetLocation(meetKey, timeline.meet.location, searchMeetHit?.location)
    : null;
  const headerDateRangeLine = timeline
    ? formatMvpMeetDateRangeReadable(timeline.meet) ||
      formatMvpMeetDateRangeReadable(searchMeetHit)
    : null;
  const showTimelineTab = mvpMeetShowsTimelineTab(timeline?.meet);
  const varsityScheduleUrl = useMemo(
    () => varsityOfficialScheduleUrlForMeetKey(meetKey),
    [meetKey]
  );
  const canAutoRefreshLive = Boolean(timeline) && scheduleStatus.tone === "live";

  useEffect(() => {
    if (varsityScheduleUrl && tab === "timeline") setTab("results");
  }, [varsityScheduleUrl, tab, meetKey]);

  const refreshLiveMvpData = useCallback(async () => {
    const k = meetKeyRef.current;
    const s = sidRef.current;
    const [tlRes, rRes] = await Promise.allSettled([
      mvpTimeline(k, s),
      mvpResults(k, s),
    ]);
    if (meetKeyRef.current !== k) return;
    if (tlRes.status === "fulfilled") setTimeline(tlRes.value);
    if (rRes.status === "fulfilled") setResults(rRes.value.results);
  }, []);

  useMvpLiveAutoRefresh(autoRefreshLiveScores, canAutoRefreshLive, refreshLiveMvpData);

  const loading = tab === "timeline" ? loadingT : loadingR;
  const err = tab === "timeline" ? errT : errR;

  return (
    <div className="mx-auto max-w-lg px-4 pb-16 pt-6">
      <Link href="/" className="mb-4 inline-block text-sm font-medium text-[var(--brand-bright)]">
        ← Home
      </Link>

      {timeline && headerNameLine && (
        <header className="relative mb-4 overflow-hidden rounded-2xl border border-lime-300/40 bg-gradient-to-r from-sky-500 via-cyan-300 to-teal-200 px-4 py-3 text-white shadow-lg shadow-black/10 ring-1 ring-white/10">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-gradient-to-r from-black/24 via-black/10 to-black/28"
          />
          <div className="relative z-10 flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h1 className="text-lg font-semibold uppercase leading-tight tracking-wide text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.55)]">
                {headerNameLine}
              </h1>
              {(headerLocationLine || headerDateRangeLine) && (
                <p className="mt-1.5 truncate text-xs font-medium text-white/90 drop-shadow-[0_1px_2px_rgba(0,0,0,0.45)]">
                  {headerLocationLine}
                  {headerLocationLine && headerDateRangeLine ? " · " : ""}
                  {headerDateRangeLine}
                </p>
              )}
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
        </header>
      )}

      <MvpInstallHintBanner tightTop />

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

      {canAutoRefreshLive && (
        <label className="mb-4 flex items-center gap-1.5 text-xs text-slate-700">
          <input
            type="checkbox"
            checked={autoRefreshLiveScores}
            onChange={(e) => setAutoRefreshLiveScores(e.target.checked)}
            className="rounded"
          />
          Auto-refresh live scores
        </label>
      )}

      <div className="mb-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-100/90 shadow-sm ring-1 ring-slate-200/60">
        <MvpMeetResultsScheduleTabs
          meetKey={meetKey}
          tab={tab}
          onTabChange={setTab}
          showInAppTimelineTab={showTimelineTab}
        />
        {!showTimelineTab && tab === "results" && !varsityScheduleUrl && (
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 bg-slate-50/95 px-3 py-2">
            <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Results</h2>
            <div className="flex flex-wrap items-center gap-2">
              {showResultsRoundPills ? (
                <MvpResultsRoundPills
                  value={resultsRoundTab}
                  onChange={(v) => {
                    resultsRoundTabInitializedRef.current = true;
                    setResultsRoundTab(v);
                  }}
                />
              ) : null}
              {!loadingR && (
                <p className="text-xs text-[var(--muted)]">{displayResultRows.length} teams</p>
              )}
            </div>
          </div>
        )}
      </div>

      {loading && <p className="text-sm text-[var(--muted)]">Loading…</p>}
      {err && timeline && <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{err}</p>}

      {!loadingT && tab === "timeline" && timeline && (
        <p className="mt-1 text-xs text-[var(--muted)]">
          {displayTimelineItems.filter((i) => !i.is_break).length} routines
        </p>
      )}

      {!loading &&
        tab === "timeline" &&
        timeline &&
        displayTimelineItems.filter((i) => !i.is_break).length === 0 && (
          <div className="mt-2 rounded-xl border border-sky-200 bg-sky-50/90 px-3 py-2.5 text-sm text-slate-800 shadow-sm">
            {scheduleStatus.tone === "upcoming" ? (
              <>
                <p className="font-semibold text-slate-900">This competition hasn’t started yet</p>
                {meetStartsReadable && (
                  <p className="mt-1 text-xs leading-snug text-slate-600">Scheduled: {meetStartsReadable}</p>
                )}
                <p className="mt-1.5 text-xs leading-snug text-slate-600">
                  {varsityScheduleUrl ? (
                    <>
                      Use <span className="font-medium">Schedule</span> above for Varsity’s official schedule on the
                      next screen.
                    </>
                  ) : (
                    <>
                      Open <span className="font-medium">Schedule</span> to see mat order when that data is available.
                    </>
                  )}
                </p>
              </>
            ) : (
              <>
                <p className="font-semibold text-slate-900">No routine list in the feed yet</p>
                <p className="mt-1 text-xs leading-snug text-slate-600">
                  We’re not seeing scored divisions or a published mat order for this meet in the Varsity results
                  API. Check back after performances begin.
                </p>
              </>
            )}
          </div>
        )}

      {!loading && tab === "timeline" && timeline && (
        <ol className="space-y-2">
          {displayTimelineItems.map((row) => {
            const when = mvpTimelineWhenDisplay(row);
            if (row.is_break) {
              return (
                <li
                  key={row.performance_id}
                  className="flex items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-3 py-3 text-sm text-[var(--muted)]"
                >
                  <span className="w-14 shrink-0 font-mono text-xs" title={when.title}>
                    {when.text}
                  </span>
                  <span>{row.break_label || "Break"}</span>
                </li>
              );
            }
            const st = statusTone(row.status, row.final_score);
            const sessionLine = row.session_name?.trim() || "";
            const extraLevelDiv = mvpResultRowMetaExtras(sessionLine, row.team_level, row.team_division);
            const roundBit = row.round?.trim();
            const extraMeta = [
              ...extraLevelDiv,
              ...(roundBit && !sessionLine.toLowerCase().includes(roundBit.toLowerCase()) ? [roundBit] : []),
            ];
            return (
              <li
                key={row.performance_id}
                className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-sm"
              >
                <div className="w-14 shrink-0 font-mono text-xs text-[var(--muted)]" title={when.title}>
                  {when.text}
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

      {tab === "results" && (
        <>
          {(showTimelineTab || varsityScheduleUrl) && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              {showResultsRoundPills ? (
                <MvpResultsRoundPills
                  value={resultsRoundTab}
                  onChange={(v) => {
                    resultsRoundTabInitializedRef.current = true;
                    setResultsRoundTab(v);
                  }}
                />
              ) : null}
              {!loadingR && (
                <p className="text-xs text-[var(--muted)]">{displayResultRows.length} teams</p>
              )}
            </div>
          )}
          {!loading && (
            <>
              {TALLY_FEEDBACK_FORM_ID &&
                !contextualFeedbackDismissed &&
                !err &&
                displayResultRows.length > 0 && (
                  <div className="relative mt-2 rounded-lg border border-slate-200 bg-slate-50 py-2 pl-2.5 pr-9 text-[11px] leading-snug text-slate-600">
                    <button
                      type="button"
                      onClick={() => dismissContextualFeedbackHelpful()}
                      className="absolute right-1 top-1 flex h-7 w-7 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200/80 hover:text-slate-800"
                      aria-label="Dismiss"
                    >
                      <span className="text-lg leading-none" aria-hidden="true">
                        ×
                      </span>
                    </button>
                    <p>
                      💬 Was this helpful? Tap{" "}
                      <button
                        type="button"
                        onClick={() => openTallyFeedback()}
                        className="font-semibold text-red-700 underline decoration-red-300 underline-offset-2 hover:text-red-800"
                      >
                        Feedback
                      </button>{" "}
                      (bottom right) — takes under a minute.
                    </p>
                  </div>
                )}
              <ol className="mt-2 space-y-2">
              {displayResultRows.length === 0 ? (
                results.length === 0 ? (
                  <div className="rounded-xl border border-sky-200 bg-sky-50/90 px-3 py-2.5 text-sm text-slate-800 shadow-sm">
                    <p className="font-semibold text-slate-900">No scores in the feed yet</p>
                    <p className="mt-1 text-xs leading-snug text-slate-600">
                      Scores show up after Varsity publishes them for this meet.{" "}
                      {showResultsRoundPills
                        ? "If the event is live, try the Prelims pill—Finals may stay empty until those rounds are posted."
                        : "If the event is live, check back as more rounds post."}
                    </p>
                    <p className="mt-1.5 text-xs leading-snug text-slate-600">
                      {varsityScheduleUrl ? (
                        <>
                          Use <span className="font-medium">Schedule</span> above for Varsity’s official schedule on the
                          next screen.
                        </>
                      ) : (
                        <>
                          Open <span className="font-medium">Schedule</span> to see mat order when that data is
                          available.
                        </>
                      )}
                    </p>
                    {TALLY_FEEDBACK_FORM_ID ? (
                      <p className="mt-3 text-xs text-slate-600">
                        💬 Expecting scores here or something look wrong? Tap{" "}
                        <button
                          type="button"
                          onClick={() => openTallyFeedback()}
                          className="font-semibold text-sky-900 underline decoration-sky-400/60 underline-offset-2 hover:text-sky-950"
                        >
                          Feedback
                        </button>
                        .
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-sm text-[var(--muted)]">
                    {showResultsRoundPills
                      ? "Nothing in this round yet. Try the other Finals / Prelims pill."
                      : "Nothing in this round for the current session."}
                  </p>
                )
              ) : (
                displayResultRows.map((r, idx) => {
                  const sessionLine = r.session_name?.trim() || "";
                  const extras = mvpResultRowMetaExtras(sessionLine, r.team_level, r.team_division);
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
                        {(() => {
                          const cap = mvpResultRowScheduleCaption(r);
                          return cap ? (
                            <div className="mt-1 text-[10px] font-medium tabular-nums text-slate-600">{cap}</div>
                          ) : null;
                        })()}
                      </div>
                      <MvpResultScoreBreakdown r={r} showRankOrdinal={false} />
                    </li>
                  );
                })
              )}
            </ol>
            </>
          )}
        </>
      )}
    </div>
  );
}
