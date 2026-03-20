"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchScores, fetchMeets, fetchMeetSessions, fetchMeetAthletes } from "@/lib/api";
import type { ScoreRow, ScoresResponse, EventKey, MeetInfo, MeetSummary, MeetSessionSummary } from "@/lib/types";
import { EVENTS } from "@/lib/types";
import { ScoreCard } from "./ScoreCard";

/** Default meet (2026 Indiana Optional State); override with NEXT_PUBLIC_DEFAULT_MEET_KEY if needed. */
const DEFAULT_MEET_KEY = process.env.NEXT_PUBLIC_DEFAULT_MEET_KEY ?? "MSO-36541";
/** Shown in the meet dropdown if this meet is not in the API list yet (e.g. before ingest upsert). */
const DEFAULT_MEET_LABEL = "2026 Indiana Optional State Championships";
const REFRESH_INTERVAL_MS = 60_000;

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

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchScores(activeMeetKey, { level, division, gym, session: sessionId, athlete, limit: 500 });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load scores");
    } finally {
      setLoading(false);
    }
  }, [activeMeetKey, level, division, gym, sessionId, athlete]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const nav = window.navigator as Navigator & { standalone?: boolean };
    const ios = /iphone|ipad|ipod/i.test(nav.userAgent);
    const standalone = window.matchMedia("(display-mode: standalone)").matches || Boolean(nav.standalone);
    const previouslyInstalled = window.localStorage.getItem("gym-scores-installed") === "1";
    setIsIos(ios);
    setIsStandalone(standalone);
    setHideInstallHint(previouslyInstalled || standalone);

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
      window.localStorage.setItem("gym-scores-installed", "1");
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
    const choice = await deferredInstallPrompt.userChoice;
    if (choice.outcome === "accepted") {
      setHideInstallHint(true);
      window.localStorage.setItem("gym-scores-installed", "1");
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
    (async () => {
      try {
        const list = await fetchMeets();
        setMeets(list);
        // Keep the configured default meet even if it is not in the API list yet (run ingest to upsert).
        if (
          list.length &&
          !list.some((m) => m.meet_id === activeMeetKey) &&
          activeMeetKey !== DEFAULT_MEET_KEY
        ) {
          setActiveMeetKey(list[0].meet_id);
        }
      } catch {
        // ignore meet list errors in UI
      }
    })();
  }, [activeMeetKey]);

  useEffect(() => {
    (async () => {
      setSessions([]);
      setSessionId("All");
      try {
        const list = await fetchMeetSessions(activeMeetKey);
        setSessions(list);
      } catch {
        // ignore sessions errors in UI
      }
    })();
  }, [activeMeetKey]);

  useEffect(() => {
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

  const levels = data
    ? ["All", ...sortLevelOptions(data.rows.map((r) => r.level).filter(Boolean) as string[]).filter((l) => l !== "All")]
    : ["All"];
  const divisions = data
    ? [
        "All",
        ...[...new Set(data.rows.map((r) => r.division).filter(Boolean))]
          .map((v) => v.trim())
          .filter(Boolean)
          .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" })),
      ]
    : ["All"];
  const gyms =
    data && data.rows.some((r) => r.gym)
      ? [
          "All",
          ...[...new Set(data.rows.map((r) => r.gym).map((g) => g.trim()).filter(Boolean))].sort((a, b) =>
            a.localeCompare(b, undefined, { sensitivity: "base" }),
          ),
        ]
      : ["All"];
  const sorted = data ? sortByEvent(data.rows, event) : [];
  const selectedMeetInList = meets.some((m) => m.meet_id === activeMeetKey);
  const showNoScoresYet =
    Boolean(data && !error && !loading && data.rows.length === 0);

  return (
    <div className="mx-auto max-w-lg px-4 pb-12 pt-6">
      <header className="rounded-2xl bg-[var(--brand)] px-4 py-3 text-white shadow-lg">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold uppercase tracking-wide opacity-90">
              {meetInfo?.name || meetName || "Meet Scores"}
            </p>
            {(locationLine || dateRangeLine) && (
              <p className="mt-0.5 truncate text-xs opacity-80">
                {locationLine}
                {locationLine && dateRangeLine ? " · " : ""}
                {dateRangeLine}
              </p>
            )}
          </div>
          <span
            className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${
              status.tone === "live"
                ? "bg-red-500 text-white"
                : status.tone === "upcoming"
                ? "bg-amber-400 text-black"
                : "bg-white/15 text-white"
            }`}
          >
            {status.label}
          </span>
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
        <div className="mb-2 flex items-center justify-between gap-2">
          <label className="flex flex-1 items-center gap-2 text-xs font-medium text-slate-700">
            <span className="whitespace-nowrap">Meet</span>
            <div className="relative w-full">
              <select
                value={activeMeetKey}
                onChange={(e) => setActiveMeetKey(e.target.value)}
                className="w-full appearance-none rounded-full border border-slate-300 bg-white px-3 py-1.5 pr-8 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                {!selectedMeetInList && (
                  <option value={activeMeetKey}>
                    {meetInfo?.name || meetName || (activeMeetKey === DEFAULT_MEET_KEY ? DEFAULT_MEET_LABEL : null) || activeMeetKey}
                  </option>
                )}
                {meets.map((m) => (
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
        </div>
        <p className="mb-1 text-[11px] leading-snug text-slate-500">
          <span className="font-semibold text-slate-600">About results: </span>
          Scores from <strong>public sources</strong> are entered and updated <strong>by the meet director</strong>, on
          their own timeline. This app only reflects what appears there after we pull data—timing and completeness are{" "}
          <strong>not controlled by us</strong>.
        </p>
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
          className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          role="status"
        >
          <p className="font-semibold">No scores yet for this meet</p>
          <p className="mt-1 text-amber-900/90">
            Nothing is in our database for this meet yet—often because the director hasn&apos;t published scores to{" "}
            <strong>public sources</strong> yet, or our sync hasn&apos;t run. Even when public listings show names or
            &quot;in progress,&quot; full scores appear only when the meet staff post them.
          </p>
        </div>
      )}

      {data && (
        <>
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
                <ScoreCard row={row} event={event} rank={i + 1} showPastResults={showPastResults} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
