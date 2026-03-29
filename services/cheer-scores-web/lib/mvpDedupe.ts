import type { MvpResultRow, MvpTimelineItem } from "./mvpTypes";

export function mvpGymMatches(selectedGym: string, rowGym: string | null | undefined): boolean {
  if (selectedGym === "All") return true;
  return (rowGym ?? "").trim().toLowerCase() === selectedGym.trim().toLowerCase();
}

/** Strip trailing round label so Prelims / Finals share one dedupe bucket. */
export function stripSessionRoundSuffix(sessionName: string): string {
  return sessionName
    .replace(/\s+(prelims?|semi-?finals?|finals?)\s*$/i, "")
    .trim();
}

function stemNorm(s: string): string {
  return stripSessionRoundSuffix(s).trim().toLowerCase();
}

/**
 * Level/division strings to show next to ``session_name`` on result cards.
 * Skips chips that only repeat the same division with a different Prelims/Finals suffix (Varsity ingest often
 * sets ``session_name`` to one round and ``team_division`` to another).
 */
export function mvpResultRowMetaExtras(
  sessionName: string,
  teamLevel: string | null | undefined,
  teamDivision: string | null | undefined
): string[] {
  const sessionLine = sessionName.trim();
  const sStem = sessionLine ? stemNorm(sessionLine) : "";
  const out: string[] = [];
  for (const raw of [teamLevel, teamDivision]) {
    if (!raw) continue;
    const bit = String(raw).trim();
    if (!bit) continue;
    if (sessionLine && sessionLine.toLowerCase().includes(bit.toLowerCase())) continue;
    if (sStem && sStem === stemNorm(bit)) continue;
    out.push(bit);
  }
  return out;
}

/** Higher score = more important round when picking one row per team+division. */
export function roundPriority(sessionName: string, round: string | null | undefined): number {
  const t = `${sessionName} ${round ?? ""}`.toLowerCase();
  if (/\bfinals?\b/.test(t) && !/semi/.test(t)) return 4;
  if (/semi/.test(t)) return 3;
  if (/prelims?/.test(t)) return 2;
  return 1;
}

/** True when session/round text is a finals round (not semi-finals). */
export function mvpResultIsFinalsRound(r: Pick<MvpResultRow, "session_name" | "round">): boolean {
  return roundPriority(r.session_name, r.round) === 4;
}

export type MvpResultsRoundTab = "finals" | "prelims";

/** Whether the result set includes scored rows for each round tab (before `filterMvpResultsByRoundTab`). */
export function mvpResultsRoundAvailability(rows: MvpResultRow[]): {
  hasFinals: boolean;
  hasPrelims: boolean;
} {
  let hasFinals = false;
  let hasPrelims = false;
  for (const r of rows) {
    if (mvpResultIsFinalsRound(r)) hasFinals = true;
    else hasPrelims = true;
    if (hasFinals && hasPrelims) break;
  }
  return { hasFinals, hasPrelims };
}

/** Filter API rows for Finals vs Prelims (prelims tab includes semi-finals and unlabeled rounds). */
export function filterMvpResultsByRoundTab(
  rows: MvpResultRow[],
  tab: MvpResultsRoundTab
): MvpResultRow[] {
  return rows.filter((r) => (tab === "finals" ? mvpResultIsFinalsRound(r) : !mvpResultIsFinalsRound(r)));
}

/**
 * Default Results tab: prefer Finals whenever that round has any scores (published cheer finals
 * are the usual “official” outcome). Prelims-only → prelims; neither → finals (empty state).
 */
export function mvpSuggestResultsRoundTab(rows: MvpResultRow[]): MvpResultsRoundTab {
  const { hasFinals, hasPrelims } = mvpResultsRoundAvailability(rows);
  if (!hasFinals && hasPrelims) return "prelims";
  return "finals";
}

function timelineDedupeKey(row: MvpTimelineItem): string {
  const stem = stripSessionRoundSuffix(row.session_name).toLowerCase();
  const tid = row.team_id != null ? `id:${row.team_id}` : "";
  const gym = (row.team_gym_name ?? "").trim().toLowerCase();
  const team = (row.team_name ?? "").trim().toLowerCase();
  return `${tid}\0${team}\0${gym}\0${stem}`;
}

function pickBetterTimeline(a: MvpTimelineItem, b: MvpTimelineItem): MvpTimelineItem {
  const pa = roundPriority(a.session_name, a.round);
  const pb = roundPriority(b.session_name, b.round);
  if (pb !== pa) return pb > pa ? b : a;
  const sa = a.final_score ?? -1;
  const sb = b.final_score ?? -1;
  if (sb !== sa) return sb > sa ? b : a;
  if (a.session_display_order !== b.session_display_order) {
    return a.session_display_order < b.session_display_order ? a : b;
  }
  return a.display_order <= b.display_order ? a : b;
}

/**
 * One card per team per division stem (e.g. merge Prelims + Finals from Varsity ingest).
 */
export function dedupeMvpTimelineItems(items: MvpTimelineItem[]): MvpTimelineItem[] {
  const breaks = items.filter((i) => i.is_break);
  const perfs = items.filter((i) => !i.is_break);
  const byKey = new Map<string, MvpTimelineItem[]>();
  for (const p of perfs) {
    const k = timelineDedupeKey(p);
    if (!byKey.has(k)) byKey.set(k, []);
    byKey.get(k)!.push(p);
  }
  const merged = [...byKey.values()].map((g) => g.reduce((a, b) => pickBetterTimeline(a, b)));
  merged.sort((a, b) => {
    if (a.session_display_order !== b.session_display_order) {
      return a.session_display_order - b.session_display_order;
    }
    return a.display_order - b.display_order;
  });
  return [...merged, ...breaks];
}

/**
 * Bucket for “same scored mat / division block”. Use session id only: every performance in one Varsity
 * table shares one MVP session, while team-level / division strings can be null or inconsistent across
 * rows and would incorrectly split standings when drilling into a team.
 */
export function mvpResultDivisionBucketKey(r: MvpResultRow): string {
  return String(r.session_id);
}

function resultDedupeKey(r: MvpResultRow): string {
  const stem = stripSessionRoundSuffix(r.session_name).toLowerCase();
  const gym = (r.team_gym_name ?? "").trim().toLowerCase();
  const team = r.team_name.trim().toLowerCase();
  return `${team}\0${gym}\0${stem}`;
}

function pickBetterResult(a: MvpResultRow, b: MvpResultRow): MvpResultRow {
  const pa = roundPriority(a.session_name, a.round);
  const pb = roundPriority(b.session_name, b.round);
  if (pb !== pa) return pb > pa ? b : a;
  const ra = a.rank ?? 9999;
  const rb = b.rank ?? 9999;
  if (ra !== rb) return ra < rb ? a : b;
  return b.final_score >= a.final_score ? b : a;
}

export function dedupeMvpResultRows(rows: MvpResultRow[]): MvpResultRow[] {
  const byKey = new Map<string, MvpResultRow[]>();
  for (const r of rows) {
    const k = resultDedupeKey(r);
    if (!byKey.has(k)) byKey.set(k, []);
    byKey.get(k)!.push(r);
  }
  const merged = [...byKey.values()].map((g) => g.reduce((a, b) => pickBetterResult(a, b)));
  merged.sort((a, b) => {
    const ra = a.rank ?? 9999;
    const rb = b.rank ?? 9999;
    if (ra !== rb) return ra - rb;
    return b.final_score - a.final_score;
  });
  return merged;
}

/** Leaderboard order: best score first, then API rank, then team name. */
export function sortMvpResultsStandings(rows: MvpResultRow[]): MvpResultRow[] {
  return [...rows].sort((a, b) => {
    if (b.final_score !== a.final_score) return b.final_score - a.final_score;
    const ra = a.rank ?? 9999;
    const rb = b.rank ?? 9999;
    if (ra !== rb) return ra - rb;
    return a.team_name.localeCompare(b.team_name);
  });
}

/** After dedupe, assign consecutive 1…n so the list reads first through last. */
export function withSequentialResultRanks(rows: MvpResultRow[]): MvpResultRow[] {
  return sortMvpResultsStandings(rows).map((r, i) => ({ ...r, rank: i + 1 }));
}
