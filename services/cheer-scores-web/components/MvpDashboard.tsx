"use client";

import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { mvpResults, mvpSearch, mvpTimeline } from "@/lib/mvpApi";
import { MVP_DEFAULT_GYM_FILTER, MVP_DEFAULT_MEET_KEY, MVP_DEFAULT_MEET_LABEL } from "@/lib/mvpDefaults";
import {
  dedupeMvpResultRows,
  dedupeMvpTimelineItems,
  filterMvpResultsByRoundTab,
  mvpGymMatches,
  mvpResultDivisionBucketKey,
  mvpResultRowMetaExtras,
  mvpResultsRoundAvailability,
  mvpSuggestResultsRoundTab,
  sortMvpResultsStandings,
  type MvpResultsRoundTab,
} from "@/lib/mvpDedupe";
import {
  formatMvpMeetDateRangeReadable,
  formatMvpMeetStartsAtReadable,
  getMvpMeetHitPickerBucket,
  getMvpMeetScheduleStatus,
  mvpCoalesceMeetLocation,
  mvpMeetHeaderNameLine,
  mvpMeetShowsTimelineTab,
  mvpMeetHeaderTitle,
  mvpMeetPickerLabel,
  mvpMeetSummaryToHit,
  mvpResultRowScheduleCaption,
  mvpTimelineWhenDisplay,
  type MvpMeetPickerTimeBucket,
} from "@/lib/mvpMeetDisplay";
import type {
  MvpMeetHit,
  MvpMeetSummary,
  MvpResultRow,
  MvpTimelineItem,
  MvpTimelineResponse,
} from "@/lib/mvpTypes";
import { pushMvpRecent } from "@/lib/mvpRecents";
import { MvpResultScoreBreakdown } from "@/components/MvpResultScoreBreakdown";
import { MvpAboutBanner } from "@/components/MvpAboutBanner";
import { MvpInstallHintBanner } from "@/components/MvpPwaInstallProvider";
import { MvpResultsRoundPills } from "@/components/MvpResultsRoundPills";
import { MvpMeetResultsScheduleTabs } from "@/components/MvpMeetResultsScheduleTabs";
import { varsityOfficialScheduleUrlForMeetKey } from "@/lib/mvpVarsityLinks";
import { openTallyFeedback, TALLY_FEEDBACK_FORM_ID } from "@/lib/feedback";
import { useMvpLiveAutoRefresh } from "@/lib/useMvpLiveAutoRefresh";

const DEFAULT_MEET_KEY = MVP_DEFAULT_MEET_KEY;
const DEFAULT_MEET_LABEL = MVP_DEFAULT_MEET_LABEL;

function inferStateFromLocation(loc: string | null | undefined): string | null {
  if (!loc) return null;
  const m = /,\s*([A-Z]{2})\s*$/i.exec(loc.trim());
  return m ? m[1].toUpperCase() : null;
}

/** Parse `starts_at` or `start_date` for sorting (ms since epoch). */
function mvpMeetSortTimestamp(m: MvpMeetHit): number {
  const raw =
    (m.starts_at ?? "").trim() ||
    (m.start_date ? `${m.start_date}T12:00:00` : "") ||
    (m.ends_at ?? "").trim() ||
    (m.end_date ? `${m.end_date}T12:00:00` : "");
  if (!raw) return 0;
  const t = Date.parse(raw.includes("T") ? raw : `${raw}T12:00:00`);
  return Number.isFinite(t) ? t : 0;
}

const MEET_PICKER_TIME_SECTIONS: readonly { key: MvpMeetPickerTimeBucket; label: string }[] = [
  { key: "upcoming", label: "Upcoming" },
  { key: "recent", label: "Recent" },
  { key: "past", label: "Past" },
];

function buildMeetPickerTimeSections(
  meets: MvpMeetHit[],
  defaultMeetKey: string
): Array<{ key: string; label: string; meets: MvpMeetHit[] }> {
  const buckets: Record<MvpMeetPickerTimeBucket, MvpMeetHit[]> = {
    upcoming: [],
    recent: [],
    past: [],
  };
  for (const m of meets) {
    buckets[getMvpMeetHitPickerBucket(m)].push(m);
  }

  const pinDefaultFirst = (rows: MvpMeetHit[]) => {
    const di = rows.findIndex((x) => x.meet_key === defaultMeetKey);
    if (di <= 0) return rows;
    const next = [...rows];
    const [d] = next.splice(di, 1);
    return [d, ...next];
  };

  return MEET_PICKER_TIME_SECTIONS.map(({ key, label }) => {
    let rows = [...buckets[key]];
    if (key === "upcoming") {
      rows.sort((a, b) => mvpMeetSortTimestamp(a) - mvpMeetSortTimestamp(b));
    } else {
      rows.sort((a, b) => mvpMeetSortTimestamp(b) - mvpMeetSortTimestamp(a));
    }
    rows = pinDefaultFirst(rows);
    return { key, label, meets: rows };
  }).filter((s) => s.meets.length > 0);
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

function inferMvpCategory(teamLevel: string | null | undefined, teamDivision: string | null | undefined): string {
  const both = `${teamLevel ?? ""} ${teamDivision ?? ""}`.toLowerCase();
  if (both.includes("cheerabilities")) return "CheerAbilities";
  if (both.includes("novice")) return "Novice";
  if (both.includes("rec")) return "Rec";
  if (both.includes("prep")) return "Prep";
  const levelMatch = /\blevel\s*([0-9]+)\b/i.exec(`${teamLevel ?? ""} ${teamDivision ?? ""}`);
  if (levelMatch) return `Level ${levelMatch[1]}`;
  const lMatch = /\bl\s*([0-9]+)\b/i.exec(`${teamLevel ?? ""} ${teamDivision ?? ""}`);
  if (lMatch) return `Level ${lMatch[1]}`;
  return "Other";
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
  if (rank === 1 || rank === 2 || rank === 3) return "border-slate-200 bg-white";
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
  gymFilter: string,
  categoryFilter: string
): boolean {
  if (sid != null && r.session_id !== sid) return false;
  if (RESTORE_LEVEL_FILTER && levelFilter !== "All" && (r.team_level ?? "") !== levelFilter) return false;
  if (!mvpGymMatches(gymFilter, r.team_gym_name)) return false;
  if (categoryFilter !== "All" && inferMvpCategory(r.team_level, r.team_division) !== categoryFilter) return false;
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

function mvpFeedbackHelpfulDismissStorageKey(meetKey: string) {
  return `cheer-mvp-feedback-helpful-dismissed-${meetKey}`;
}

export function MvpDashboard() {
  const [meetList, setMeetList] = useState<MvpMeetHit[]>([]);
  const [meetsErr, setMeetsErr] = useState<string | null>(null);
  const [meetStateFilter, setMeetStateFilter] = useState("All");
  const [activeMeetKey, setActiveMeetKey] = useState(DEFAULT_MEET_KEY);
  const [meetPickerOpen, setMeetPickerOpen] = useState(false);
  const [meetSearch, setMeetSearch] = useState("");
  const meetPickerRef = useRef<HTMLDivElement>(null);

  const [sessionId, setSessionId] = useState<number | "">("");
  const [level, setLevel] = useState("All");
  const [gym, setGym] = useState(MVP_DEFAULT_GYM_FILTER);
  const [team, setTeam] = useState("All");
  const [category, setCategory] = useState("All");
  const [tab, setTab] = useState<"timeline" | "results">("results");
  const [resultsRoundTab, setResultsRoundTab] = useState<MvpResultsRoundTab>("finals");

  const [timeline, setTimeline] = useState<MvpTimelineResponse | null>(null);
  const [allResults, setAllResults] = useState<MvpResultRow[]>([]);
  const [loadingT, setLoadingT] = useState(true);
  const [loadingR, setLoadingR] = useState(true);
  const [errT, setErrT] = useState<string | null>(null);
  const [errR, setErrR] = useState<string | null>(null);

  const [contextualFeedbackDismissed, setContextualFeedbackDismissed] = useState(false);
  const [autoRefreshLiveScores, setAutoRefreshLiveScores] = useState(true);
  const activeMeetKeyRef = useRef(activeMeetKey);
  activeMeetKeyRef.current = activeMeetKey;
  const resultsRoundTabInitializedRef = useRef(false);

  useLayoutEffect(() => {
    resultsRoundTabInitializedRef.current = false;
    setSessionId("");
    setLevel("All");
    setGym(MVP_DEFAULT_GYM_FILTER);
    setCategory("All");
    setTimeline(null);
    setAllResults([]);
    setErrT(null);
    setErrR(null);
    setLoadingT(true);
    setLoadingR(true);
    setResultsRoundTab("finals");
    setTab("results");
  }, [activeMeetKey]);

  useEffect(() => {
    if (!timeline?.meet) return;
    if (!mvpMeetShowsTimelineTab(timeline.meet)) setTab("results");
  }, [timeline]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const k = mvpFeedbackHelpfulDismissStorageKey(activeMeetKey);
      setContextualFeedbackDismissed(window.localStorage.getItem(k) === "1");
    } catch {
      setContextualFeedbackDismissed(false);
    }
  }, [activeMeetKey]);

  const dismissContextualFeedbackHelpful = useCallback(() => {
    try {
      window.localStorage.setItem(mvpFeedbackHelpfulDismissStorageKey(activeMeetKey), "1");
    } catch {
      /* ignore */
    }
    setContextualFeedbackDismissed(true);
  }, [activeMeetKey]);

  /** Full meet catalog for the picker; gym filter only narrows schedule/results, not this list. */
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
    return [...states].sort((a, b) => a.localeCompare(b));
  }, [meetList]);

  const meetPickerOptions = useMemo((): MvpMeetHit[] => {
    const filtered =
      meetStateFilter === "All"
        ? meetList
        : meetList.filter((m) => inferStateFromLocation(m.location) === meetStateFilter);
    if (filtered.some((m) => m.meet_key === DEFAULT_MEET_KEY)) return filtered;
    if (meetStateFilter !== "All") return filtered;
    const synthetic: MvpMeetHit = {
      meet_key: DEFAULT_MEET_KEY,
      name: DEFAULT_MEET_LABEL,
      location: null,
      start_date: null,
      end_date: null,
    };
    return [synthetic, ...filtered];
  }, [meetList, meetStateFilter]);

  const meetPickerFiltered = useMemo(() => {
    const q = meetSearch.trim().toLowerCase();
    if (!q) return meetPickerOptions;
    return meetPickerOptions.filter((m) => {
      const label = mvpMeetPickerLabel(m).toLowerCase();
      const key = m.meet_key.toLowerCase();
      const loc = (m.location ?? "").toLowerCase();
      return label.includes(q) || key.includes(q) || loc.includes(q);
    });
  }, [meetPickerOptions, meetSearch]);

  const meetPickerSections = useMemo(
    () => buildMeetPickerTimeSections(meetPickerFiltered, DEFAULT_MEET_KEY),
    [meetPickerFiltered]
  );

  useEffect(() => {
    if (!meetPickerOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (meetPickerRef.current && !meetPickerRef.current.contains(e.target as Node)) {
        setMeetPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [meetPickerOpen]);

  useEffect(() => {
    if (!meetPickerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMeetPickerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [meetPickerOpen]);

  useEffect(() => {
    if (!meetPickerOpen) setMeetSearch("");
  }, [meetPickerOpen]);

  useEffect(() => {
    if (meetPickerOptions.length === 0) return;
    if (!meetPickerOptions.some((m) => m.meet_key === activeMeetKey)) {
      setActiveMeetKey(meetPickerOptions[0].meet_key);
    }
  }, [meetPickerOptions, activeMeetKey]);

  const selectedMeetInList = meetPickerOptions.some((m) => m.meet_key === activeMeetKey);

  const meetPickerTriggerLabel = useMemo(() => {
    if (!selectedMeetInList) return null;
    const m = meetPickerOptions.find((x) => x.meet_key === activeMeetKey);
    return m ? mvpMeetPickerLabel(m) : null;
  }, [selectedMeetInList, meetPickerOptions, activeMeetKey]);

  const meetHitForSchedule = useMemo(
    () => meetList.find((m) => m.meet_key === activeMeetKey) ?? null,
    [meetList, activeMeetKey]
  );

  const scheduleToneResolved = useMemo((): "live" | "upcoming" | "past" | null => {
    if (timeline?.meet) return getMvpMeetScheduleStatus(timeline.meet).tone;
    if (meetHitForSchedule) {
      return getMvpMeetScheduleStatus(meetHitForSchedule as MvpMeetSummary).tone;
    }
    return null;
  }, [timeline?.meet, meetHitForSchedule]);

  const sid = sessionId === "" ? null : sessionId;

  /**
   * Gym in the dropdown is always ``gym``. For **past** meets only, after results are loaded,
   * if no row in the meet is from that gym, widen to All so the list is not blank (dropdown
   * still shows the user’s gym). While loading or when results are still empty, keep ``gym`` so
   * we do not flash “all gyms” or a false “no rows for your gym” message.
   */
  const filterGym = useMemo(() => {
    if (gym === "All") return gym;
    if (scheduleToneResolved !== "past") return gym;
    if (loadingR || allResults.length === 0) return gym;
    const hasRowsForGym = allResults.some((r) => mvpGymMatches(gym, r.team_gym_name));
    return hasRowsForGym ? gym : "All";
  }, [scheduleToneResolved, gym, allResults, loadingR]);

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

  /** Gym dropdown: only gyms that appear on the loaded meet (timeline + results), plus current filter if set. */
  const gymPickerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const i of optionSourceRows) {
      const gn = (i.team_gym_name ?? "").trim();
      if (gn && notSentinelAll(gn)) set.add(gn);
    }
    if (gym !== "All" && gym.trim()) set.add(gym.trim());
    return ["All", ...[...set].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }))];
  }, [optionSourceRows, gym]);

  const teamOptionRows = useMemo(() => {
    return optionSourceRows.filter((i) => {
      if (filterGym !== "All" && !mvpGymMatches(filterGym, i.team_gym_name)) return false;
      if (category !== "All" && inferMvpCategory(i.team_level, i.team_division) !== category) return false;
      return true;
    });
  }, [optionSourceRows, filterGym, category]);

  const teams = useMemo(() => {
    const rest = [
      ...new Set(teamOptionRows.map((i) => i.team_name).filter(Boolean) as string[]),
    ]
      .filter(notSentinelAll)
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    return ["All", ...rest];
  }, [teamOptionRows]);

  const categories = useMemo(() => {
    const fixedPrefix = ["CheerAbilities", "Novice", "Rec", "Prep"];
    const rowsForCategories =
      filterGym === "All"
        ? optionSourceRows
        : optionSourceRows.filter((r) => mvpGymMatches(filterGym, r.team_gym_name));
    const present = new Set<string>();
    for (const r of rowsForCategories) {
      present.add(inferMvpCategory(r.team_level, r.team_division));
    }
    const levelNums = new Set<number>();
    for (const c of present) {
      const m = /^Level (\d+)$/.exec(c);
      if (m) levelNums.add(Number(m[1]));
    }
    const levelLabels = [...levelNums].sort((a, b) => a - b).map((n) => `Level ${n}`);

    const out: string[] = ["All"];
    for (const c of fixedPrefix) {
      if (present.has(c)) out.push(c);
    }
    for (const c of levelLabels) {
      if (present.has(c)) out.push(c);
    }
    if (present.has("Other")) out.push("Other");
    return out;
  }, [optionSourceRows, filterGym]);

  useLayoutEffect(() => {
    if (category !== "All" && !categories.includes(category)) setCategory("All");
  }, [categories, category]);

  useLayoutEffect(() => {
    if (team === "All") return;
    if (!teams.includes(team)) setTeam("All");
  }, [filterGym, category, teams, team]);

  const filteredTimelineItems: MvpTimelineItem[] = useMemo(() => {
    const items = timeline?.items ?? [];
    return items.filter((row) => {
      if (row.is_break) {
        return sid == null || row.session_id === sid;
      }
      if (sid != null && row.session_id !== sid) return false;
      if (RESTORE_LEVEL_FILTER && level !== "All" && (row.team_level ?? "") !== level) return false;
      if (!mvpGymMatches(filterGym, row.team_gym_name)) return false;
      if (category !== "All" && inferMvpCategory(row.team_level, row.team_division) !== category) return false;
      if (team !== "All" && (row.team_name ?? "") !== team) return false;
      return true;
    });
  }, [timeline, sid, level, filterGym, category, team]);

  const divisionFilteredResults: MvpResultRow[] = useMemo(() => {
    const narrowContext = allResults.filter((r) =>
      matchesMvpResultRowFilters(r, sid, level, filterGym, category)
    );
    if (team === "All") return narrowContext;

    // Anchors respect gym (and session/level) so "Gym X + Team Y" finds the right division.
    const anchors = narrowContext.filter((r) => r.team_name === team);
    if (anchors.length === 0) return [];

    const buckets = new Set(anchors.map((r) => mvpResultDivisionBucketKey(r)));
    // Full standings: every team in that session/level/division, not only the selected gym.
    const widePool = allResults.filter((r) =>
      matchesMvpResultRowFilters(r, sid, level, "All", category)
    );
    return widePool.filter((r) => buckets.has(mvpResultDivisionBucketKey(r)));
  }, [allResults, sid, level, filterGym, category, team]);

  const filteredResults: MvpResultRow[] = useMemo(
    () => filterMvpResultsByRoundTab(divisionFilteredResults, resultsRoundTab),
    [divisionFilteredResults, resultsRoundTab]
  );

  const { hasFinals: hasFinalsRoundScores, hasPrelims: hasPrelimsRoundScores } = useMemo(
    () => mvpResultsRoundAvailability(divisionFilteredResults),
    [divisionFilteredResults]
  );
  const showResultsRoundPills = hasFinalsRoundScores && hasPrelimsRoundScores;

  useEffect(() => {
    if (allResults.length > 0 && !resultsRoundTabInitializedRef.current) {
      setResultsRoundTab(mvpSuggestResultsRoundTab(allResults));
      resultsRoundTabInitializedRef.current = true;
    }
  }, [allResults]);

  useEffect(() => {
    if (!hasFinalsRoundScores && hasPrelimsRoundScores && resultsRoundTab === "finals") {
      setResultsRoundTab("prelims");
    }
    if (hasFinalsRoundScores && !hasPrelimsRoundScores && resultsRoundTab === "prelims") {
      setResultsRoundTab("finals");
    }
  }, [hasFinalsRoundScores, hasPrelimsRoundScores, resultsRoundTab]);

  const displayTimelineItems = useMemo(
    () => dedupeMvpTimelineItems(filteredTimelineItems),
    [filteredTimelineItems]
  );
  const displayResultRows = useMemo(() => {
    const deduped = dedupeMvpResultRows(filteredResults);
    if (team === "All") return deduped;
    // Full division standings: keep Varsity ranks; only sort for display order.
    return sortMvpResultsStandings(deduped);
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
  const canAutoRefreshLive = Boolean(timeline) && scheduleStatus.tone === "live";
  const meetStartsReadable = formatMvpMeetStartsAtReadable(meetInfo ?? null);
  const selectedMeetSummary = useMemo(
    () => meetPickerOptions.find((m) => m.meet_key === activeMeetKey) ?? null,
    [meetPickerOptions, activeMeetKey]
  );
  const searchListMeet = useMemo(
    () => meetList.find((m) => m.meet_key === activeMeetKey) ?? null,
    [meetList, activeMeetKey]
  );
  const headerLocationLine = mvpCoalesceMeetLocation(
    activeMeetKey,
    meetInfo?.location,
    selectedMeetSummary?.location,
    searchListMeet?.location
  );
  const headerDateRangeLine =
    formatMvpMeetDateRangeReadable(meetInfo) ||
    formatMvpMeetDateRangeReadable(selectedMeetSummary) ||
    formatMvpMeetDateRangeReadable(searchListMeet);
  const showTimelineTab = mvpMeetShowsTimelineTab(meetInfo);
  const varsityScheduleUrl = useMemo(
    () => varsityOfficialScheduleUrlForMeetKey(activeMeetKey),
    [activeMeetKey]
  );

  useEffect(() => {
    if (varsityScheduleUrl && tab === "timeline") setTab("results");
  }, [varsityScheduleUrl, tab, activeMeetKey]);

  const refreshLiveMvpData = useCallback(async () => {
    const key = activeMeetKeyRef.current;
    const [tlRes, rRes] = await Promise.allSettled([
      mvpTimeline(key, null),
      mvpResults(key, null),
    ]);
    if (activeMeetKeyRef.current !== key) return;
    if (tlRes.status === "fulfilled") setTimeline(tlRes.value);
    if (rRes.status === "fulfilled") setAllResults(rRes.value.results);
  }, []);

  useMvpLiveAutoRefresh(autoRefreshLiveScores, canAutoRefreshLive, refreshLiveMvpData);

  const loading = tab === "timeline" ? loadingT : loadingR;
  const err = tab === "timeline" ? errT : errR;

  return (
    <div className="mx-auto max-w-lg px-4 pb-16 pt-6">
      <header className="relative overflow-hidden rounded-2xl border border-lime-300/40 bg-gradient-to-r from-sky-500 via-cyan-300 to-teal-200 px-4 py-3 text-white shadow-lg shadow-black/10 ring-1 ring-white/10">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-r from-black/24 via-black/10 to-black/28"
        />
        <div className="relative z-10 flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold uppercase leading-tight tracking-wide text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.55)]">
              {headerNameLine}
            </h1>
            {!meetInfo && !loadingT && (
              <p className="mt-1 text-sm text-white/90 drop-shadow-[0_1px_1px_rgba(0,0,0,0.45)]">
                Select a competition below
              </p>
            )}
            {(headerLocationLine || headerDateRangeLine) && (
              <p className="mt-1.5 truncate text-xs font-medium text-white/90 drop-shadow-[0_1px_2px_rgba(0,0,0,0.45)]">
                {headerLocationLine}
                {headerLocationLine && headerDateRangeLine ? " · " : ""}
                {headerDateRangeLine}
              </p>
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
      </header>

      <MvpInstallHintBanner />

      <MvpAboutBanner />

      <div className="mt-4 rounded-2xl bg-[var(--card)] p-3 shadow-sm ring-1 ring-slate-200/80">
        {meetsErr && (
          <p className="mb-2 rounded-lg bg-amber-50 px-2 py-1.5 text-xs text-amber-900">{meetsErr}</p>
        )}

        <div className="mb-2 grid grid-cols-3 gap-1.5 sm:gap-2">
          {RESTORE_SESSION_FILTER && (
            <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-700">
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
            <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-700">
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
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Category</span>
            <div className="relative min-w-0">
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="mvp-select mvp-select-sm min-w-0"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500" />
            </div>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Gym</span>
            <div className="relative min-w-0">
              <select
                value={gym}
                onChange={(e) => setGym(e.target.value)}
                className="mvp-select mvp-select-sm min-w-0"
                title="Filter schedule and results by gym (only gyms in this competition). Persists when you change meets. For past meets with no rows for your gym, results temporarily show all teams."
              >
                {gymPickerOptions.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-2.5 w-2.5 -translate-y-1/2 text-slate-500" />
            </div>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Team</span>
            <div className="relative min-w-0">
              <select
                value={team}
                onChange={(e) => setTeam(e.target.value)}
                className="mvp-select mvp-select-sm min-w-0"
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

        {filterGym !== gym && !loadingR && allResults.length > 0 && (
          <p className="mb-2 text-xs leading-snug text-slate-600">
            No results for <span className="font-medium text-slate-800">{gym}</span> in this meet;
            showing all teams. Your gym filter is unchanged for the next competition.
          </p>
        )}

        <div className="mb-2 flex items-end gap-2">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span id="mvp-meet-field-label" className="text-xs font-medium text-slate-700">
              Meet
            </span>
            <div ref={meetPickerRef} className="relative w-full">
              <button
                type="button"
                id="mvp-meet-picker-trigger"
                aria-haspopup="listbox"
                aria-expanded={meetPickerOpen}
                aria-controls="mvp-meet-picker-listbox"
                aria-labelledby="mvp-meet-field-label"
                onClick={() => setMeetPickerOpen((o) => !o)}
                className="mvp-select flex w-full items-center justify-between gap-2 text-left"
              >
                <span className="min-w-0 flex-1 truncate">
                  {meetPickerTriggerLabel ?? meetPickerFallbackTitle}
                </span>
                <ChevronDown className="pointer-events-none h-3 w-3 shrink-0 text-slate-500" />
              </button>
              {meetPickerOpen && (
                <div
                  id="mvp-meet-picker-listbox"
                  role="listbox"
                  aria-labelledby="mvp-meet-picker-trigger"
                  className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[min(22rem,70vh)] overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg ring-1 ring-black/5"
                >
                  <div className="border-b border-slate-100 px-2 pb-2 pt-1">
                    <input
                      type="search"
                      value={meetSearch}
                      onChange={(e) => setMeetSearch(e.target.value)}
                      placeholder="Search name, state, or id — finds future meets too"
                      className="w-full rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-sm text-slate-900 outline-none ring-[var(--brand)] placeholder:text-slate-400 focus:border-slate-300 focus:bg-white focus:ring-2"
                      autoComplete="off"
                      autoFocus
                    />
                  </div>
                  <ul className="max-h-60 overflow-y-auto px-1 pb-1">
                    {!selectedMeetInList && (
                      <li>
                        <button
                          type="button"
                          role="option"
                          aria-selected={true}
                          className="w-full rounded-lg px-2 py-2 text-left text-sm text-slate-800"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => setMeetPickerOpen(false)}
                        >
                          {meetPickerFallbackTitle}
                        </button>
                      </li>
                    )}
                    {meetPickerFiltered.length === 0 ? (
                      <li className="px-2 py-3 text-center text-sm text-slate-500">No matches</li>
                    ) : (
                      <>
                        {meetPickerSections.map((g) => (
                          <Fragment key={g.key}>
                            <li
                              role="presentation"
                              className="sticky top-0 z-[1] border-b border-slate-100 bg-slate-50/95 px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500 backdrop-blur-sm"
                            >
                              {g.label}
                            </li>
                            {g.meets.map((m) => {
                              const selected = m.meet_key === activeMeetKey;
                              return (
                                <li key={m.meet_key}>
                                  <button
                                    type="button"
                                    role="option"
                                    aria-selected={selected}
                                    className={`w-full rounded-lg px-2 py-2 text-left text-sm ${
                                      selected
                                        ? "bg-sky-100 font-semibold text-slate-900"
                                        : "text-slate-800 hover:bg-slate-50"
                                    }`}
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => {
                                      setMeetPickerOpen(false);
                                      setActiveMeetKey(m.meet_key);
                                    }}
                                  >
                                    {mvpMeetPickerLabel(m)}
                                  </button>
                                </li>
                              );
                            })}
                          </Fragment>
                        ))}
                      </>
                    )}
                  </ul>
                </div>
              )}
            </div>
          </div>
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

        {canAutoRefreshLive && (
          <label className="mb-2 mt-1 flex items-center gap-1.5 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={autoRefreshLiveScores}
              onChange={(e) => setAutoRefreshLiveScores(e.target.checked)}
              className="rounded"
            />
            Auto-refresh live scores
          </label>
        )}

        <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-slate-100/90 shadow-sm ring-1 ring-slate-200/60">
          <MvpMeetResultsScheduleTabs
            meetKey={activeMeetKey}
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
          {timeline && tab === "results" && (showTimelineTab || varsityScheduleUrl) && (
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

          {!loading &&
            tab === "timeline" &&
            timeline &&
            displayTimelineItems.filter((i) => !i.is_break).length === 0 && (
              <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50/90 px-3 py-2.5 text-sm text-slate-800 shadow-sm">
                {scheduleStatus.tone === "upcoming" ? (
                  <>
                    <p className="font-semibold text-slate-900">This competition hasn’t started yet</p>
                    {meetStartsReadable && (
                      <p className="mt-1 text-xs leading-snug text-slate-600">
                        Scheduled: {meetStartsReadable}
                      </p>
                    )}
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
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-slate-900">No routine list in the feed yet</p>
                    <p className="mt-1 text-xs leading-snug text-slate-600">
                      We’re not seeing scored divisions or a published mat order for this meet in the Varsity
                      results API. Check back after performances begin.
                    </p>
                  </>
                )}
              </div>
            )}

          {!loading && tab === "timeline" && timeline && (
            <ol className="mt-2 space-y-2">
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
                    <div
                      className="w-14 shrink-0 font-mono text-xs text-[var(--muted)]"
                      title={when.title}
                    >
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

          {!loading && tab === "results" && (
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
                allResults.length === 0 ? (
                  <div className="rounded-xl border border-sky-200 bg-sky-50/90 px-3 py-2.5 text-sm text-slate-800 shadow-sm">
                    <p className="font-semibold text-slate-900">No scores in the feed yet</p>
                    <p className="mt-1 text-xs leading-snug text-slate-600">
                      Scores appear here after Varsity publishes them for this meet.{" "}
                      {showResultsRoundPills
                        ? "If the event is running, try the Prelims pill—Finals can stay empty until those rounds post."
                        : "If the event is running, check back as more rounds post."}
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
                    No teams match the current gym, category, team, or round. Try All
                    {showResultsRoundPills ? " or switch Finals / Prelims." : " or widen filters."}
                  </p>
                )
              ) : (
                displayResultRows.map((r, idx) => {
                  const sessionLine = r.session_name?.trim() || "";
                  const extras = mvpResultRowMetaExtras(sessionLine, r.team_level, r.team_division);
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
                        {(() => {
                          const cap = mvpResultRowScheduleCaption(r);
                          return cap ? (
                            <div className="mt-1 text-[10px] font-medium tabular-nums text-slate-600">{cap}</div>
                          ) : null;
                        })()}
                      </div>
                    </div>
                    <MvpResultScoreBreakdown r={r} />
                    </button>
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
