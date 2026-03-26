"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { mvpResults, mvpSearch, mvpTimeline } from "@/lib/mvpApi";
import { MVP_DEFAULT_MEET_KEY, MVP_DEFAULT_MEET_LABEL } from "@/lib/mvpDefaults";
import {
  dedupeMvpResultRows,
  dedupeMvpTimelineItems,
  filterMvpResultsByRoundTab,
  mvpGymMatches,
  mvpResultDivisionBucketKey,
  mvpResultIsFinalsRound,
  withSequentialResultRanks,
  type MvpResultsRoundTab,
} from "@/lib/mvpDedupe";
import {
  formatMvpMeetDateRangeReadable,
  getMvpMeetScheduleStatus,
  mvpMeetHeaderNameLine,
  mvpMeetShowsTimelineTab,
  mvpMeetHeaderTitle,
  mvpMeetPickerLabel,
  mvpMeetSummaryToHit,
} from "@/lib/mvpMeetDisplay";
import type { MvpMeetHit, MvpResultRow, MvpTimelineItem, MvpTimelineResponse } from "@/lib/mvpTypes";
import { pushMvpRecent } from "@/lib/mvpRecents";
import { MvpResultScoreBreakdown } from "@/components/MvpResultScoreBreakdown";

const DEFAULT_MEET_KEY = MVP_DEFAULT_MEET_KEY;
const DEFAULT_MEET_LABEL = MVP_DEFAULT_MEET_LABEL;
const DEFAULT_MEET_STATE = (process.env.NEXT_PUBLIC_DEFAULT_MEET_STATE ?? "GA").trim() || "GA";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

function inferStateFromLocation(loc: string | null | undefined): string | null {
  if (!loc) return null;
  const m = /,\s*([A-Z]{2})\s*$/i.exec(loc.trim());
  return m ? m[1].toUpperCase() : null;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function sortLevelOptions(levelValues: string[]): string[] {
  const unique = [...new Set(levelValues.map((v) => v.trim()).filter(Boolean))];
  const numeric: Array<{ value: string; num: number }> = [];
  const letters: string[] = [];
  for (const v of unique) {
    if (/^\d+$/.test(v)) {
      numeric.push({ value: v, num: Number(v) });
    } else {
      letters.push(v);
    }
  }
  numeric.sort((a, b) => b.num - a.num);
  letters.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));
  return [...numeric.map((n) => n.value), ...letters];
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

function resultRankCardClass(rank: number | null): string {
  if (rank === 1) return "border-amber-200 bg-[var(--medal-gold-bg)]";
  if (rank === 2) return "border-slate-300 bg-[var(--medal-silver-bg)]";
  if (rank === 3) return "border-orange-200 bg-[var(--medal-bronze-bg)]";
  return "border-slate-200 bg-white";
}

const notSentinelAll = (s: string) => s.trim().toLowerCase() !== "all";

/** Set `true` to bring back the Session dropdown (long lists were overwhelming). */
const RESTORE_SESSION_FILTER = false;
/** Set `true` to bring back Level (redundant with Division — Division was removed). */
const RESTORE_LEVEL_FILTER = false;

function matchesMvpResultRowFilters(
  r: MvpResultRow,
  sid: number | null,
  levelFilter: string,
  gymFilter: string
): boolean {
  if (sid != null && r.session_id !== sid) return false;
  if (RESTORE_LEVEL_FILTER && levelFilter !== "All" && (r.team_level ?? "") !== levelFilter) return false;
  if (!mvpGymMatches(gymFilter, r.team_gym_name)) return false;
  return true;
}

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      className={className}
      viewBox="0 0 20 20"
      fill="none"
    >
      <path
        d="M6 8l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function MvpDashboard() {
  const [meetList, setMeetList] = useState<MvpMeetHit[]>([]);
  const [meetsErr, setMeetsErr] = useState<string | null>(null);
  const [meetStateFilter, setMeetStateFilter] = useState("All");
  const [activeMeetKey, setActiveMeetKey] = useState(DEFAULT_MEET_KEY);

  const [sessionId, setSessionId] = useState<number | "">("");
  const [level, setLevel] = useState("All");
  const [gym, setGym] = useState("All");
  const [team, setTeam] = useState("All");
  const [tab, setTab] = useState<"timeline" | "results">("timeline");
  const [resultsRoundTab, setResultsRoundTab] = useState<MvpResultsRoundTab>("finals");

  const [timeline, setTimeline] = useState<MvpTimelineResponse | null>(null);
  const [allResults, setAllResults] = useState<MvpResultRow[]>([]);
  const [loadingT, setLoadingT] = useState(true);
  const [loadingR, setLoadingR] = useState(true);
  const [errT, setErrT] = useState<string | null>(null);
  const [errR, setErrR] = useState<string | null>(null);

  const [deferredInstallPrompt, setDeferredInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isIos, setIsIos] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);
  const [hideInstallHint, setHideInstallHint] = useState(false);

  useLayoutEffect(() => {
    setSessionId("");
    setLevel("All");
    setGym("All");
    setTeam("All");
    setTimeline(null);
    setAllResults([]);
    setErrT(null);
    setErrR(null);
    setLoadingT(true);
    setLoadingR(true);
    setResultsRoundTab("finals");
  }, [activeMeetKey]);

  useEffect(() => {
    if (!timeline?.meet) return;
    if (!mvpMeetShowsTimelineTab(timeline.meet)) setTab("results");
  }, [timeline]);

  useEffect(() => {
    if (allResults.length === 0) return;
    if (!allResults.some(mvpResultIsFinalsRound)) setResultsRoundTab("prelims");
  }, [activeMeetKey, allResults]);

  useEffect(() => {
    let cancelled = false;
    setMeetsErr(null);
    (async () => {
      try {
        const res = await mvpSearch("");
        if (cancelled) return;
        setMeetList(res.meets);
      } catch (e) {
        if (cancelled) return;
        setMeetList([]);
        setMeetsErr(e instanceof Error ? e.message : "Failed to load meets");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const nav = window.navigator as Navigator & { standalone?: boolean };
    const ios = /iphone|ipad|ipod/i.test(nav.userAgent);
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches || Boolean(nav.standalone);
    const previouslyInstalled = window.localStorage.getItem("cheer-mvp-installed") === "1";
    setIsIos(ios);
    setIsStandalone(standalone);
    setHideInstallHint(previouslyInstalled || standalone);

    if ("serviceWorker" in nav) {
      if (process.env.NODE_ENV === "production") {
        void nav.serviceWorker.register("/sw.js");
      } else {
        void nav.serviceWorker.getRegistrations().then((regs) => {
          regs.forEach((reg) => void reg.unregister());
        });
        if ("caches" in window) {
          void caches.keys().then((keys) => {
            keys.forEach((key) => void caches.delete(key));
          });
        }
      }
    }

    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setDeferredInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const onInstalled = () => {
      setDeferredInstallPrompt(null);
      setIsStandalone(true);
      setHideInstallHint(true);
      window.localStorage.setItem("cheer-mvp-installed", "1");
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const onInstallClick = useCallback(async () => {
    if (!deferredInstallPrompt) return;
    await deferredInstallPrompt.prompt();
    setDeferredInstallPrompt(null);
  }, [deferredInstallPrompt]);

  useEffect(() => {
    let cancelled = false;
    setErrT(null);
    setLoadingT(true);
    (async () => {
      try {
        const tl = await mvpTimeline(activeMeetKey, null);
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
  }, [activeMeetKey]);

  useEffect(() => {
    let cancelled = false;
    setErrR(null);
    setLoadingR(true);
    (async () => {
      try {
        const res = await mvpResults(activeMeetKey, null);
        if (cancelled) return;
        setAllResults(res.results);
      } catch (e) {
        if (cancelled) return;
        setAllResults([]);
        setErrR(e instanceof Error ? e.message : "Failed to load results");
      } finally {
        if (!cancelled) setLoadingR(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeMeetKey]);

  const meetStatesForPicker = useMemo(() => {
    const states = new Set<string>();
    for (const m of meetList) {
      const s = inferStateFromLocation(m.location);
      if (s) states.add(s);
    }
    states.add(DEFAULT_MEET_STATE);
    return [...states].sort((a, b) => a.localeCompare(b));
  }, [meetList]);

  const meetPickerOptions = useMemo((): MvpMeetHit[] => {
    const filtered =
      meetStateFilter === "All"
        ? meetList
        : meetList.filter((m) => inferStateFromLocation(m.location) === meetStateFilter);
    if (filtered.some((m) => m.meet_key === DEFAULT_MEET_KEY)) return filtered;
    const showSynthetic =
      meetStateFilter === "All" || meetStateFilter.toUpperCase() === DEFAULT_MEET_STATE.toUpperCase();
    if (!showSynthetic) return filtered;
    const synthetic: MvpMeetHit = {
      meet_key: DEFAULT_MEET_KEY,
      name: DEFAULT_MEET_LABEL,
      location: `Atlanta, ${DEFAULT_MEET_STATE}`,
      start_date: null,
      end_date: null,
    };
    return [synthetic, ...filtered];
  }, [meetList, meetStateFilter]);

  useEffect(() => {
    if (meetPickerOptions.length === 0) return;
    if (!meetPickerOptions.some((m) => m.meet_key === activeMeetKey)) {
      setActiveMeetKey(meetPickerOptions[0].meet_key);
    }
  }, [meetPickerOptions, activeMeetKey]);

  const selectedMeetInList = meetPickerOptions.some((m) => m.meet_key === activeMeetKey);

  const optionSourceRows = useMemo(() => {
    type Row = {
      team_level: string | null;
      team_division: string | null;
      team_gym_name: string | null;
      team_name: string | null;
    };
    const rows: Row[] = [];
    for (const i of timeline?.items ?? []) {
      if (!i.is_break) {
        rows.push({
          team_level: i.team_level,
          team_division: i.team_division,
          team_gym_name: i.team_gym_name,
          team_name: i.team_name,
        });
      }
    }
    for (const r of allResults) {
      rows.push({
        team_level: r.team_level,
        team_division: r.team_division,
        team_gym_name: r.team_gym_name,
        team_name: r.team_name,
      });
    }
    return rows;
  }, [timeline, allResults]);

  const levels = useMemo(() => {
    const raw = optionSourceRows.map((i) => i.team_level).filter(Boolean) as string[];
    return ["All", ...sortLevelOptions(raw).filter(notSentinelAll)];
  }, [optionSourceRows]);

  const gyms = useMemo(() => {
    const rest = [
      ...new Set(optionSourceRows.map((i) => i.team_gym_name).filter(Boolean) as string[]),
    ]
      .map((g) => g.trim())
      .filter(Boolean)
      .filter(notSentinelAll)
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    return ["All", ...rest];
  }, [optionSourceRows]);

  const teamOptionRows = useMemo(() => {
    if (gym === "All") return optionSourceRows;
    return optionSourceRows.filter((i) => mvpGymMatches(gym, i.team_gym_name));
  }, [optionSourceRows, gym]);

  const teams = useMemo(() => {
    const rest = [
      ...new Set(teamOptionRows.map((i) => i.team_name).filter(Boolean) as string[]),
    ]
      .filter(notSentinelAll)
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    return ["All", ...rest];
  }, [teamOptionRows]);

  useLayoutEffect(() => {
    if (team === "All") return;
    if (!teams.includes(team)) setTeam("All");
  }, [gym, teams, team]);

  const sid = sessionId === "" ? null : sessionId;

  const filteredTimelineItems: MvpTimelineItem[] = useMemo(() => {
    const items = timeline?.items ?? [];
    return items.filter((row) => {
      if (row.is_break) {
        return sid == null || row.session_id === sid;
      }
      if (sid != null && row.session_id !== sid) return false;
      if (RESTORE_LEVEL_FILTER && level !== "All" && (row.team_level ?? "") !== level) return false;
      if (!mvpGymMatches(gym, row.team_gym_name)) return false;
      if (team !== "All" && (row.team_name ?? "") !== team) return false;
      return true;
    });
  }, [timeline, sid, level, gym, team]);

  const divisionFilteredResults: MvpResultRow[] = useMemo(() => {
    const narrowContext = allResults.filter((r) => matchesMvpResultRowFilters(r, sid, level, gym));
    if (team === "All") return narrowContext;

    // Anchors respect gym (and session/level) so "Gym X + Team Y" finds the right division.
    const anchors = narrowContext.filter((r) => r.team_name === team);
    if (anchors.length === 0) return [];

    const buckets = new Set(anchors.map((r) => mvpResultDivisionBucketKey(r)));
    // Full standings: every team in that session/level/division, not only the selected gym.
    const widePool = allResults.filter((r) => matchesMvpResultRowFilters(r, sid, level, "All"));
    return widePool.filter((r) => buckets.has(mvpResultDivisionBucketKey(r)));
  }, [allResults, sid, level, gym, team]);

  const filteredResults: MvpResultRow[] = useMemo(
    () => filterMvpResultsByRoundTab(divisionFilteredResults, resultsRoundTab),
    [divisionFilteredResults, resultsRoundTab]
  );

  const displayTimelineItems = useMemo(
    () => dedupeMvpTimelineItems(filteredTimelineItems),
    [filteredTimelineItems]
  );
  const displayResultRows = useMemo(() => {
    const deduped = dedupeMvpResultRows(filteredResults);
    if (team === "All") return deduped;
    return withSequentialResultRanks(deduped);
  }, [filteredResults, team]);

  const meetInfo = timeline?.meet;
  const headerNameLine = mvpMeetHeaderNameLine(meetInfo, activeMeetKey, DEFAULT_MEET_KEY, DEFAULT_MEET_LABEL);
  const meetPickerFallbackTitle = mvpMeetHeaderTitle(
    meetInfo,
    activeMeetKey,
    DEFAULT_MEET_KEY,
    DEFAULT_MEET_LABEL
  );
  const scheduleStatus = getMvpMeetScheduleStatus(meetInfo ?? null);
  const headerLocationLine = (meetInfo?.location ?? "").trim() || null;
  const headerDateRangeLine = formatMvpMeetDateRangeReadable(meetInfo);
  const showTimelineTab = mvpMeetShowsTimelineTab(meetInfo);

  const loading = tab === "timeline" ? loadingT : loadingR;
  const err = tab === "timeline" ? errT : errR;

  return (
    <div className="mx-auto max-w-lg px-4 pb-16 pt-6">
      <header className="rounded-2xl bg-gradient-to-br from-[var(--brand)] via-[#003d52] to-[var(--brand-bright)] px-4 py-4 text-white shadow-lg">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-bold uppercase leading-tight tracking-wide">{headerNameLine}</h1>
            {!meetInfo && !loadingT && (
              <p className="mt-1 text-sm opacity-75">Select a competition below</p>
            )}
          </div>
          {meetInfo && scheduleStatus.tone !== "past" && (
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

      <div className="mt-4 rounded-2xl bg-[var(--card)] p-3 shadow-sm ring-1 ring-slate-200/80">
        {!isStandalone && !hideInstallHint && (
          <div className="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-700">
            {deferredInstallPrompt ? (
              <div className="flex items-center justify-between gap-2">
                <span>Install this app on your home screen for quick access.</span>
                <button
                  type="button"
                  onClick={() => void onInstallClick()}
                  className="shrink-0 rounded-full bg-[var(--accent)] px-3 py-1.5 text-xs font-bold text-[var(--accent-foreground)]"
                >
                  Add app
                </button>
              </div>
            ) : isIos ? (
              <div className="space-y-1">
                <p className="font-semibold text-slate-900">Install on iPhone:</p>
                <p>
                  Tap Share, then <strong>Add to Home Screen</strong>.
                </p>
              </div>
            ) : (
              <p>Tip: add this site to your home screen for quick access.</p>
            )}
          </div>
        )}

        {meetsErr && (
          <p className="mb-2 rounded-lg bg-amber-50 px-2 py-1.5 text-xs text-amber-900">{meetsErr}</p>
        )}

        <div className="mb-2 flex items-end gap-2">
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Meet</span>
            <div className="relative w-full">
              <select
                value={activeMeetKey}
                onChange={(e) => setActiveMeetKey(e.target.value)}
                className="mvp-select"
              >
                {!selectedMeetInList && (
                  <option value={activeMeetKey}>
                    {meetPickerFallbackTitle}
                  </option>
                )}
                {meetPickerOptions.map((m) => (
                  <option key={m.meet_key} value={m.meet_key}>
                    {mvpMeetPickerLabel(m)}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500" />
            </div>
          </label>
          <label className="flex w-[5.25rem] shrink-0 flex-col gap-1 text-xs font-medium text-slate-700 sm:w-24">
            <span>State</span>
            <div className="relative w-full">
              <select
                value={meetStateFilter}
                onChange={(e) => setMeetStateFilter(e.target.value)}
                className="mvp-select mvp-select-sm"
                title="Filter meets by state"
              >
                <option value="All">All states</option>
                {meetStatesForPicker.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500" />
            </div>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {RESTORE_SESSION_FILTER && (
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
              <span>Session</span>
              <div className="relative">
                <select
                  value={sessionId === "" ? "" : String(sessionId)}
                  onChange={(e) => {
                    const v = e.target.value;
                    setSessionId(v === "" ? "" : Number(v));
                  }}
                  className="mvp-select mvp-select-sm"
                >
                  <option value="">All</option>
                  {(timeline?.sessions ?? []).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500" />
              </div>
            </label>
          )}
          {RESTORE_LEVEL_FILTER && (
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
              <span>Level</span>
              <div className="relative">
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                  className="mvp-select mvp-select-sm"
                >
                  {levels.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500" />
              </div>
            </label>
          )}
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Gym</span>
            <div className="relative">
              <select
                value={gym}
                onChange={(e) => setGym(e.target.value)}
                className="mvp-select mvp-select-sm"
              >
                {gyms.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500" />
            </div>
          </label>
          <label className="col-span-2 flex flex-col gap-1 text-xs font-medium text-slate-700 sm:col-span-1">
            <span>Team</span>
            <div className="relative">
              <select
                value={team}
                onChange={(e) => setTeam(e.target.value)}
                className="mvp-select mvp-select-sm"
              >
                {teams.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500" />
            </div>
          </label>
        </div>

        <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-slate-100/90 shadow-sm ring-1 ring-slate-200/60">
          {showTimelineTab ? (
            <div className="flex gap-1 p-1">
              <button
                type="button"
                onClick={() => setTab("timeline")}
                className={`flex-1 rounded-full py-2 text-xs font-bold uppercase tracking-wide ${
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
                className={`flex-1 rounded-full py-2 text-xs font-bold uppercase tracking-wide ${
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
              className="bg-[var(--accent)] px-3 py-2 text-center text-xs font-bold uppercase tracking-wide text-[var(--accent-foreground)]"
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
                className={`flex-1 rounded-full py-1.5 text-[11px] font-bold uppercase tracking-wide ${
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
                className={`flex-1 rounded-full py-1.5 text-[11px] font-bold uppercase tracking-wide ${
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
      </div>

      {!timeline && loadingT && <p className="mt-4 text-sm text-[var(--muted)]">Loading meet…</p>}
      {errT && !timeline && (
        <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{errT}</p>
      )}

      {timeline && (
        <>
          {loading && <p className="mt-4 text-sm text-[var(--muted)]">Loading…</p>}
          {err && timeline && (
            <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{err}</p>
          )}

          {tab === "timeline" && !loadingT && (
            <p className="mt-3 text-xs text-[var(--muted)]">
              {displayTimelineItems.filter((i) => !i.is_break).length} routines
            </p>
          )}
          {tab === "results" && !loadingR && (
            <p className="mt-3 text-xs text-[var(--muted)]">{displayResultRows.length} teams</p>
          )}

          {!loading && tab === "timeline" && timeline && (
            <ol className="mt-2 space-y-2">
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
            <ol className="mt-2 space-y-2">
              {displayResultRows.length === 0 ? (
                <p className="text-sm text-[var(--muted)]">No scored routines for this filter yet.</p>
              ) : (
                displayResultRows.map((r, idx) => {
                  const sessionLine = r.session_name?.trim() || "";
                  const extras = [r.team_level, r.team_division].filter(Boolean).filter(
                    (bit) => !sessionLine.toLowerCase().includes(String(bit).toLowerCase())
                  );
                  const tagBits = [sessionLine || null, ...extras].filter(Boolean) as string[];
                  return (
                  <li key={`${r.team_name}-${r.session_id}-${idx}`} className="list-none">
                    <button
                      type="button"
                      className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-3 text-left shadow-sm transition hover:brightness-[0.98] active:scale-[0.995] ${resultRankCardClass(r.rank)}`}
                      aria-label={`Show full results for ${r.team_name} in this session, level, and division`}
                      onClick={() => {
                        setTab("results");
                        setTeam(r.team_name);
                        const gn = r.team_gym_name?.trim();
                        if (gn) setGym(gn);
                      }}
                    >
                    <div className="flex min-w-0 flex-1 items-start gap-2">
                      {r.rank != null && (
                        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/80 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
                          {r.rank}
                        </span>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold text-[var(--text)]">{r.team_name}</div>
                        {r.team_gym_name && (
                          <div className="text-xs font-medium text-[var(--gym)]">{r.team_gym_name}</div>
                        )}
                        <div className="mt-0.5 flex flex-wrap gap-1 text-[10px] text-[var(--muted)]">
                          {tagBits.map((x) => (
                            <span key={x} className="rounded-full bg-slate-100 px-2 py-0.5">
                              {x}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <MvpResultScoreBreakdown r={r} />
                    </button>
                  </li>
                  );
                })
              )}
            </ol>
          )}
        </>
      )}
    </div>
  );
}
