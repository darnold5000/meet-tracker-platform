"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { fetchScores, fetchMeets, fetchMeetSessions, fetchMeetAthletes } from "@/lib/api";
import type { ScoreRow, ScoresResponse, EventKey, MeetInfo, MeetSummary, MeetSessionSummary } from "@/lib/types";
import { EVENTS } from "@/lib/types";
import { computePerEventRanks, scoreRowKey } from "@/lib/eventRanks";
import { openTallyFeedback, TALLY_FEEDBACK_FORM_ID } from "@/lib/feedback";
import { ScoreCard } from "./ScoreCard";

/** Optional default competition (`meets.meet_id`); leave unset and the first API meet is selected when the list loads. */
const DEFAULT_MEET_KEY = (process.env.NEXT_PUBLIC_DEFAULT_MEET_KEY ?? "").trim();
/** Shown in the meet dropdown if this meet is not in the API list yet (e.g. before ingest upsert). */
const DEFAULT_MEET_LABEL = (process.env.NEXT_PUBLIC_DEFAULT_MEET_LABEL ?? "").trim() || "Featured competition";
/** Postal/state code for the default meet; used with the synthetic row when State filters match. */
const DEFAULT_MEET_STATE = (process.env.NEXT_PUBLIC_DEFAULT_MEET_STATE ?? "").trim();
const DEFAULT_MEET_ENABLED = Boolean(DEFAULT_MEET_KEY);
const REFRESH_INTERVAL_MS = 60_000;
const LS_DISMISS_ABOUT_RESULTS = "cheer-scores-dismiss-about-results";
const LS_DISMISS_NO_SCORES_HINT = "cheer-scores-dismiss-no-scores-hint";
/** “About results” banner — off for now; set true to show again (still respects dismiss in localStorage). */
const SHOW_ABOUT_RESULTS_NOTICE = false;

function feedbackHelpfulDismissStorageKey(meetKey: string) {
  return `cheer-scores-feedback-helpful-dismissed-${meetKey}`;
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

/** Parse API date-only strings as local calendar dates (avoid UTC shift from `new Date("2026-03-20")`). */
function parseCalendarDate(value: string | null | undefined): Date | null {
  if (!value || typeof value !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mon = Number(m[2]) - 1;
  const d = Number(m[3]);
  if (!Number.isFinite(y) || !Number.isFinite(mon) || !Number.isFinite(d)) return null;
  return new Date(y, mon, d);
}

function getMeetStatus(meet: MeetInfo | null): { label: string; tone: "live" | "upcoming" | "past" } {
  if (!meet?.start_date) {
    return { label: "Scores", tone: "live" };
  }

  const now = new Date();
  const start = parseCalendarDate(meet.start_date) ?? new Date(meet.start_date);
  const end = meet.end_date ? parseCalendarDate(meet.end_date) ?? new Date(meet.end_date) : start;

  // Compare only calendar dates (ignore time-of-day differences)
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const endDay = new Date(end.getFullYear(), end.getMonth(), end.getDate());

  const fmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
  const rangeLabel =
    fmt.format(startDay) + (endDay.getTime() !== startDay.getTime() ? `–${fmt.format(endDay)}` : "");

  if (today >= startDay && today <= endDay) {
    return { label: "LIVE", tone: "live" };
  }
  if (today < startDay) {
    return { label: `Starts ${fmt.format(startDay)}`, tone: "upcoming" };
  }
  return { label: rangeLabel, tone: "past" };
}

function getMeetDateRangeLabel(meet: MeetInfo | null): string | null {
  if (!meet?.start_date) return null;

  const start = parseCalendarDate(meet.start_date) ?? new Date(meet.start_date);
  const end = meet.end_date ? parseCalendarDate(meet.end_date) ?? new Date(meet.end_date) : start;

  const startMonth = start.toLocaleString("en-US", { month: "short" });
  const endMonth = end.toLocaleString("en-US", { month: "short" });
  const startDay = start.getDate();
  const endDay = end.getDate();

  if (startMonth === endMonth) {
    return startDay === endDay ? `${startMonth} ${startDay}` : `${startMonth} ${startDay}-${endDay}`;
  }
  return `${startMonth} ${startDay}-${endMonth} ${endDay}`;
}

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

  // Largest number first, then any letter-based levels.
  numeric.sort((a, b) => b.num - a.num);
  letters.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));

  return [...numeric.map((n) => n.value), ...letters];
}

interface MeetViewProps {
  meetKey?: string;
  meetName?: string;
}

export function MeetView({ meetKey = DEFAULT_MEET_KEY, meetName }: MeetViewProps) {
  const [data, setData] = useState<ScoresResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meets, setMeets] = useState<MeetSummary[]>([]);
  const [meetStateFilter, setMeetStateFilter] = useState("All");
  const [meetStatesForPicker, setMeetStatesForPicker] = useState<string[]>([]);
  const [activeMeetKey, setActiveMeetKey] = useState(meetKey);
  const [sessions, setSessions] = useState<MeetSessionSummary[]>([]);
  const [sessionId, setSessionId] = useState("All");
  const [level, setLevel] = useState("All");
  const [division, setDivision] = useState("All");
  const [gym, setGym] = useState("All");
  const [athlete, setAthlete] = useState("All");
  const [athletes, setAthletes] = useState<string[]>([]);
  const [event, setEvent] = useState<EventKey>("aa");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [deferredInstallPrompt, setDeferredInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isIos, setIsIos] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);
  const [hideInstallHint, setHideInstallHint] = useState(false);
  const [showAboutResultsNotice, setShowAboutResultsNotice] = useState(SHOW_ABOUT_RESULTS_NOTICE);
  const [contextualFeedbackDismissed, setContextualFeedbackDismissed] = useState(false);
  const [showNoScoresHint, setShowNoScoresHint] = useState(true);
  /** Unfiltered score rows for building Level / Division / Gym dropdowns (filtered `data.rows` would collapse options). */
  const [filterOptionsByMeet, setFilterOptionsByMeet] = useState<{
    meetKey: string;
    rows: ScoreRow[];
  } | null>(null);

  /** When switching meets, reset filters in layout so the scores fetch effect never runs with the previous meet's session/level/etc. */
  useLayoutEffect(() => {
    setSessionId("All");
    setLevel("All");
    setDivision("All");
    setGym("All");
    setAthlete("All");
    // Drop stale scores immediately so header/body never show the previous meet while the new request is in flight.
    setData(null);
    setError(null);
    setLoading(true);
  }, [activeMeetKey]);

  const scoresFetchGenRef = useRef(0);
  const meetsListFetchGenRef = useRef(0);

  const load = useCallback(async () => {
    if (!activeMeetKey.trim()) {
      setError(null);
      setData(null);
      setLoading(false);
      return;
    }
    setError(null);
    const gen = ++scoresFetchGenRef.current;
    try {
      const res = await fetchScores(activeMeetKey, { level, division, gym, session: sessionId, athlete, limit: 500 });
      if (gen !== scoresFetchGenRef.current) return;
      setData(res);
    } catch (e) {
      if (gen !== scoresFetchGenRef.current) return;
      setError(e instanceof Error ? e.message : "Failed to load scores");
    } finally {
      if (gen === scoresFetchGenRef.current) setLoading(false);
    }
  }, [activeMeetKey, level, division, gym, sessionId, athlete]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const nav = window.navigator as Navigator & { standalone?: boolean };
    const ios = /iphone|ipad|ipod/i.test(nav.userAgent);
    const standalone = window.matchMedia("(display-mode: standalone)").matches || Boolean(nav.standalone);
    const previouslyInstalled = window.localStorage.getItem("cheer-scores-installed") === "1";
    setIsIos(ios);
    setIsStandalone(standalone);
    setHideInstallHint(previouslyInstalled || standalone);

    if (
      SHOW_ABOUT_RESULTS_NOTICE &&
      window.localStorage.getItem(LS_DISMISS_ABOUT_RESULTS) === "1"
    ) {
      setShowAboutResultsNotice(false);
    }
    if (window.localStorage.getItem(LS_DISMISS_NO_SCORES_HINT) === "1") {
      setShowNoScoresHint(false);
    }
    if ("serviceWorker" in nav) {
      if (process.env.NODE_ENV === "production") {
        void nav.serviceWorker.register("/sw.js");
      } else {
        // Keep local dev stable: remove previously registered workers/caches.
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
      window.localStorage.setItem("cheer-scores-installed", "1");
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const k = feedbackHelpfulDismissStorageKey(activeMeetKey);
      setContextualFeedbackDismissed(window.localStorage.getItem(k) === "1");
    } catch {
      setContextualFeedbackDismissed(false);
    }
  }, [activeMeetKey]);

  const dismissAboutResultsNotice = useCallback(() => {
    setShowAboutResultsNotice(false);
    try {
      window.localStorage.setItem(LS_DISMISS_ABOUT_RESULTS, "1");
    } catch {
      /* ignore */
    }
  }, []);

  const dismissContextualFeedbackHelpful = useCallback(() => {
    try {
      window.localStorage.setItem(feedbackHelpfulDismissStorageKey(activeMeetKey), "1");
    } catch {
      /* ignore */
    }
    setContextualFeedbackDismissed(true);
  }, [activeMeetKey]);

  const dismissNoScoresHint = useCallback(() => {
    setShowNoScoresHint(false);
    try {
      window.localStorage.setItem(LS_DISMISS_NO_SCORES_HINT, "1");
    } catch {
      /* ignore */
    }
  }, []);

  const onInstallClick = useCallback(async () => {
    if (!deferredInstallPrompt) return;
    await deferredInstallPrompt.prompt();
    const choice = await deferredInstallPrompt.userChoice;
    if (choice.outcome === "accepted") {
      setHideInstallHint(true);
      window.localStorage.setItem("cheer-scores-installed", "1");
    }
    setDeferredInstallPrompt(null);
  }, [deferredInstallPrompt]);

  useEffect(() => {
    setActiveMeetKey(meetKey);
  }, [meetKey]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    // Keep filters consistent with the selected session.
    setLevel("All");
    setDivision("All");
    setGym("All");
    setAthlete("All");
  }, [sessionId]);

  useEffect(() => {
    // Keep athlete selection consistent with the other dropdown filters.
    setAthlete("All");
  }, [level, division, gym]);

  const meetInfo = data?.meet ?? null;
  const status = getMeetStatus(meetInfo);
  const locationLine = meetInfo?.location ?? meetInfo?.facility ?? meetInfo?.state ?? null;
  const dateRangeLine = getMeetDateRangeLabel(meetInfo);
  const showPastResults = status.tone === "past";
  const canAutoRefresh = status.tone === "live";

  useEffect(() => {
    if (!autoRefresh || !canAutoRefresh) return;

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (intervalId != null) return;
      if (document.visibilityState !== "visible") return;
      intervalId = setInterval(load, REFRESH_INTERVAL_MS);
    };

    const stop = () => {
      if (intervalId == null) return;
      clearInterval(intervalId);
      intervalId = null;
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        // Refresh immediately when returning to the page.
        load();
        start();
      } else {
        stop();
      }
    };

    // Start polling only when visible.
    start();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [autoRefresh, canAutoRefresh, load]);

  useEffect(() => {
    const gen = ++meetsListFetchGenRef.current;
    (async () => {
      try {
        const { meets: list, states } = await fetchMeets({
          state: meetStateFilter,
        });
        if (gen !== meetsListFetchGenRef.current) return;
        const stateKey = meetStateFilter.trim().toLowerCase();
        const normalized =
          meetStateFilter === "All"
            ? list
            : list.filter((m) => (m.state ?? "").trim().toLowerCase() === stateKey);
        setMeets(normalized);
        setMeetStatesForPicker(states);
        setActiveMeetKey((current) => {
          const filterSt = meetStateFilter.trim().toLowerCase();
          const defaultSt = DEFAULT_MEET_STATE.toLowerCase();
          const stateFilterMatchesDefault =
            DEFAULT_MEET_ENABLED &&
            Boolean(DEFAULT_MEET_STATE) &&
            filterSt === defaultSt;

          if (!normalized.length) {
            if (DEFAULT_MEET_ENABLED && meetStateFilter !== "All" && stateFilterMatchesDefault) {
              return DEFAULT_MEET_KEY;
            }
            return current;
          }
          if (!current) return normalized[0].meet_id;
          if (normalized.some((m) => m.meet_id === current)) return current;
          if (DEFAULT_MEET_ENABLED && current === DEFAULT_MEET_KEY) {
            if (meetStateFilter === "All") return current;
            if (stateFilterMatchesDefault) return current;
          }
          // Landing on the default meet’s state: prefer configured default over API sort order.
          if (DEFAULT_MEET_ENABLED && stateFilterMatchesDefault) return DEFAULT_MEET_KEY;
          return normalized[0].meet_id;
        });
      } catch {
        if (gen !== meetsListFetchGenRef.current) return;
        setMeets([]);
        setMeetStatesForPicker([]);
      }
    })();
  }, [meetStateFilter]);

  useEffect(() => {
    if (!activeMeetKey.trim()) {
      setSessions([]);
      return;
    }
    (async () => {
      setSessions([]);
      try {
        const list = await fetchMeetSessions(activeMeetKey);
        setSessions(list);
      } catch {
        // ignore sessions errors in UI
      }
    })();
  }, [activeMeetKey]);

  useEffect(() => {
    if (!activeMeetKey.trim()) {
      setAthletes([]);
      return;
    }
    (async () => {
      try {
        const list = await fetchMeetAthletes(activeMeetKey, { level, division, gym, session: sessionId });
        setAthletes(list);
      } catch {
        // ignore athletes errors in UI
        setAthletes([]);
      }
    })();
  }, [activeMeetKey, level, division, gym, sessionId]);

  useEffect(() => {
    const key = activeMeetKey;
    setFilterOptionsByMeet(null);
    if (!key.trim()) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchScores(key, { limit: 500 });
        if (!cancelled) setFilterOptionsByMeet({ meetKey: key, rows: res.rows });
      } catch {
        if (!cancelled) setFilterOptionsByMeet({ meetKey: key, rows: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeMeetKey]);

  const allScoreFiltersClear =
    level === "All" &&
    division === "All" &&
    gym === "All" &&
    sessionId === "All" &&
    athlete === "All";

  const rowsForFilterDropdowns = useMemo(() => {
    if (filterOptionsByMeet?.meetKey === activeMeetKey) return filterOptionsByMeet.rows;
    // Avoid using filtered `data.rows` for options (it collapses choices); only safe when no filters yet.
    if (allScoreFiltersClear && data?.meet_key === activeMeetKey) return data.rows;
    return [];
  }, [
    activeMeetKey,
    allScoreFiltersClear,
    data?.meet_key,
    data?.rows,
    filterOptionsByMeet,
  ]);

  const hasFilterOptionRows = rowsForFilterDropdowns.length > 0;
  /** Avoid duplicate "All" sentinel vs data values (fixes React duplicate key warnings on <option>). */
  const notSentinelAll = (s: string) => s.trim().toLowerCase() !== "all";

  const levels = hasFilterOptionRows
    ? [
        "All",
        ...sortLevelOptions(rowsForFilterDropdowns.map((r) => r.level).filter(Boolean) as string[]).filter(notSentinelAll),
      ]
    : ["All"];
  const divisions = hasFilterOptionRows
    ? (() => {
        const rest = [...new Set(rowsForFilterDropdowns.map((r) => r.division).filter(Boolean))]
          .map((v) => v.trim())
          .filter(Boolean)
          .filter(notSentinelAll)
          .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
        return ["All", ...rest];
      })()
    : ["All"];
  const gyms =
    rowsForFilterDropdowns.some((r) => r.gym)
      ? (() => {
          const rest = [...new Set(rowsForFilterDropdowns.map((r) => r.gym).map((g) => g.trim()).filter(Boolean))]
            .filter(notSentinelAll)
            .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
          return ["All", ...rest];
        })()
      : ["All"];
  const sorted = data ? sortByEvent(data.rows, event) : [];
  const eventRanksByRow = useMemo(() => {
    if (!data?.rows?.length) return new Map<string, Partial<Record<EventKey, number>>>();
    return computePerEventRanks(data.rows);
  }, [data?.rows]);
  /** API list plus synthetic default when `/api/meets` omits it and the state filter is All or matches the default meet’s state. */
  const meetPickerOptions = useMemo((): MeetSummary[] => {
    if (!DEFAULT_MEET_ENABLED) return meets;
    if (meets.some((m) => m.meet_id === DEFAULT_MEET_KEY)) return meets;
    const filterSt = meetStateFilter.trim().toLowerCase();
    const showSynthetic =
      meetStateFilter === "All" ||
      (Boolean(DEFAULT_MEET_STATE) && filterSt === DEFAULT_MEET_STATE.toLowerCase());
    if (!showSynthetic) return meets;
    const synthetic: MeetSummary = {
      meet_id: DEFAULT_MEET_KEY,
      name: DEFAULT_MEET_LABEL,
      location: null,
      facility: null,
      host_gym: null,
      state: DEFAULT_MEET_STATE || null,
      start_date: null,
      end_date: null,
    };
    return [synthetic, ...meets];
  }, [meets, meetStateFilter]);

  const selectedMeetInList = meetPickerOptions.some((m) => m.meet_id === activeMeetKey);
  const showNoScoresYet =
    Boolean(data && !error && !loading && data.rows.length === 0 && showNoScoresHint);

  return (
    <div className="mx-auto max-w-lg px-4 pb-12 pt-6">
      <header className="rounded-2xl bg-[var(--brand)] px-4 py-3 text-white shadow-lg">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold uppercase tracking-wide opacity-90">
              {meetInfo?.name || meetName || "Cheer Tracker"}
            </p>
            {(locationLine || dateRangeLine) && (
              <p className="mt-0.5 truncate text-xs opacity-80">
                {locationLine}
                {locationLine && dateRangeLine ? " · " : ""}
                {dateRangeLine}
              </p>
            )}
          </div>
          {status.tone !== "past" && (
            <span
              className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${
                status.tone === "live"
                  ? "bg-red-500 text-white"
                  : "bg-amber-400 text-black"
              }`}
            >
              {status.label}
            </span>
          )}
        </div>
      </header>

      <div className="mt-4 rounded-xl bg-white p-3 shadow-sm">
        {!isStandalone && !hideInstallHint && (
          <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-700">
            {deferredInstallPrompt ? (
              <div className="flex items-center justify-between gap-2">
                <span>Install this app on your home screen for quick access.</span>
                <button
                  type="button"
                  onClick={() => void onInstallClick()}
                  className="shrink-0 rounded-full bg-red-600 px-3 py-1.5 font-semibold text-white"
                >
                  Add app
                </button>
              </div>
            ) : isIos ? (
              <div className="space-y-1">
                <p className="font-semibold text-slate-900">Install on iPhone (2 quick steps):</p>
                <p>
                  1) Tap the Share button{" "}
                  <span aria-hidden="true" className="inline-flex items-center rounded border border-slate-300 bg-white px-1.5 py-0.5 align-middle font-semibold">
                    <svg viewBox="0 0 20 20" className="mr-1 h-3.5 w-3.5" fill="none">
                      <path
                        d="M10 13V3m0 0L6.5 6.5M10 3l3.5 3.5M4 10.5V15a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-4.5"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    Share
                  </span>
                </p>
                <p>2) Scroll down and tap <strong>Add to Home Screen</strong>.</p>
              </div>
            ) : (
              <p>Tip: if your browser supports install, you can add this app to your home screen.</p>
            )}
          </div>
        )}
        <div className="mb-2 flex items-end gap-2">
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Meet</span>
            <div className="relative w-full">
              <select
                value={activeMeetKey}
                onChange={(e) => setActiveMeetKey(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-3 py-2 pr-8 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                {!selectedMeetInList && (
                  <option value={activeMeetKey}>
                    {meetInfo?.name ||
                      meetName ||
                      (DEFAULT_MEET_ENABLED && activeMeetKey === DEFAULT_MEET_KEY ? DEFAULT_MEET_LABEL : null) ||
                      activeMeetKey}
                  </option>
                )}
                {meetPickerOptions.map((m) => (
                  <option key={m.meet_id} value={m.meet_id}>
                    {m.name || m.meet_id}
                  </option>
                ))}
              </select>
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500"
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
            </div>
          </label>
          <label className="flex w-[5.25rem] shrink-0 flex-col gap-1 text-xs font-medium text-slate-700 sm:w-24">
            <span>State</span>
            <div className="relative w-full">
              <select
                value={meetStateFilter}
                onChange={(e) => setMeetStateFilter(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-2 py-2 pr-6 text-[11px] font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
                title="Filter meets by state, or All states"
              >
                <option value="All">All states</option>
                {[...new Set(meetStatesForPicker)]
                  .filter((s) => s.trim().toLowerCase() !== "all")
                  .map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
              </select>
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500"
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
            </div>
          </label>
        </div>
        {showAboutResultsNotice && (
          <div className="relative mb-1 rounded-lg border border-slate-200 bg-slate-50 py-2 pl-2.5 pr-9 text-[11px] leading-snug text-slate-500">
            <button
              type="button"
              onClick={() => dismissAboutResultsNotice()}
              className="absolute right-1 top-1 flex h-7 w-7 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200/80 hover:text-slate-800"
              aria-label="Dismiss scoring notice"
            >
              <span className="text-lg leading-none" aria-hidden="true">
                ×
              </span>
            </button>
            <p>
              <span className="font-semibold text-slate-600">About results: </span>
              Scores from <strong>public sources</strong> are entered and updated <strong>by the meet director</strong>,
              on their own timeline. This app only reflects what appears there after we pull data—timing and
              completeness are <strong>not controlled by us</strong>.
            </p>
          </div>
        )}
        <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-2 text-xs font-medium text-slate-700">
          <label className="col-span-1 flex items-center gap-1.5">
            <span>Session</span>
            <div className="relative flex-1">
              <select
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-3 py-1.5 pr-8 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                <option value="All">All</option>
                {sessions.map((s) => (
                  <option key={s.session_id} value={s.session_id}>
                    {s.label}
                  </option>
                ))}
              </select>
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500"
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
            </div>
          </label>
          <label className="col-span-1 flex items-center gap-1.5">
            <span>Level</span>
            <div className="relative flex-1">
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-3 py-1.5 pr-8 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                {levels.map((l) => (
                  <option key={l} value={l}>
                    {l || "All"}
                  </option>
                ))}
              </select>
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500"
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
            </div>
          </label>
          <label className="col-span-1 flex items-center gap-1.5">
            <span>Division</span>
            <div className="relative flex-1">
              <select
                value={division}
                onChange={(e) => setDivision(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-3 py-1.5 pr-8 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                {divisions.map((d) => (
                  <option key={d} value={d}>
                    {d || "All"}
                  </option>
                ))}
              </select>
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500"
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
            </div>
          </label>
          <label className="col-span-1 flex items-center gap-1.5">
            <span>Gym</span>
            <div className="relative flex-1">
              <select
                value={gym}
                onChange={(e) => setGym(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-3 py-1.5 pr-8 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                {gyms.map((g) => (
                  <option key={g} value={g}>
                    {g || "All"}
                  </option>
                ))}
              </select>
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500"
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
            </div>
          </label>
          <label className="col-span-2 flex items-center gap-1.5">
            <span>Athlete</span>
            <div className="relative w-full">
              <select
                value={athlete}
                onChange={(e) => setAthlete(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-3 py-1.5 pr-8 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                <option value="All">All</option>
                {athletes.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500"
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
            </div>
          </label>
          {canAutoRefresh && (
            <label className="col-span-2 flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded"
              />
              Auto-refresh live scores
            </label>
          )}
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

      {showNoScoresYet && (
        <div
          className="relative mt-4 rounded-xl border border-amber-200 bg-amber-50 py-3 pl-4 pr-10 text-sm text-amber-950"
          role="status"
        >
          <button
            type="button"
            onClick={() => dismissNoScoresHint()}
            className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full text-amber-900/70 hover:bg-amber-200/60 hover:text-amber-950"
            aria-label="Dismiss no scores message"
          >
            <span className="text-xl leading-none" aria-hidden="true">
              ×
            </span>
          </button>
          <p className="font-semibold">No scores yet for this meet</p>
          <p className="mt-1 text-amber-900/90">
            Nothing is in our database for this meet yet—often because the director hasn&apos;t published scores to{" "}
            <strong>public sources</strong> yet, or our sync hasn&apos;t run. Even when public listings show names or
            &quot;in progress,&quot; full scores appear only when the meet staff post them.
          </p>
          {TALLY_FEEDBACK_FORM_ID ? (
            <p className="mt-3 text-xs text-amber-900/85">
              💬 Expecting scores here or something look wrong? Tap{" "}
              <button
                type="button"
                onClick={() => openTallyFeedback()}
                className="font-semibold text-amber-950 underline decoration-amber-600/50 underline-offset-2 hover:text-amber-900"
              >
                Feedback
              </button>
              .
            </p>
          ) : null}
        </div>
      )}

      {data && (
        <>
          {!showNoScoresYet &&
            TALLY_FEEDBACK_FORM_ID &&
            !contextualFeedbackDismissed &&
            data.rows.length > 0 &&
            !loading &&
            !error && (
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
          {!showNoScoresYet && (
            <p className="mt-2 text-sm font-semibold text-slate-500">{data.count} athletes</p>
          )}
          <ul className="mt-3 space-y-3">
            {sorted.map((row, i) => (
              <li
                key={[
                  row.athlete,
                  row.gym,
                  row.session ?? "",
                  row.level,
                  row.division,
                  String(i),
                ].join("|")}
              >
                <ScoreCard
                  row={row}
                  event={event}
                  rank={i + 1}
                  showPastResults={showPastResults}
                  eventRanks={eventRanksByRow.get(scoreRowKey(row))}
                />
              </li>
            ))}
          </ul>
        </>
      )}

      {TALLY_FEEDBACK_FORM_ID ? (
        <button
          type="button"
          onClick={() => openTallyFeedback()}
          title="Quick feedback — about a minute"
          className="fixed bottom-5 right-4 z-50 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-800 shadow-lg ring-1 ring-black/5 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-red-400"
          aria-label="Open feedback form (about a minute)"
        >
          💬 Feedback
        </button>
      ) : null}
    </div>
  );
}
