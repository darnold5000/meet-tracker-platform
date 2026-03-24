/** Response shape from FastAPI GET /api/meet/{meet_key}/scores */
export interface ScoreRow {
  athlete: string;
  gym: string;
  session: string | null;
  level: string;
  division: string;
  aa: { score: number | null; place: number | null };
  vt: { score: number | null; place: number | null };
  ub: { score: number | null; place: number | null };
  bb: { score: number | null; place: number | null };
  fx: { score: number | null; place: number | null };
}

export interface MeetInfo {
  name: string | null;
  location: string | null;
  facility: string | null;
  host_gym: string | null;
  state: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface ScoresResponse {
  meet_key: string;
  meet: MeetInfo | null;
  latest: unknown;
  count: number;
  rows: ScoreRow[];
}

export interface MeetSummary {
  meet_id: string;
  name: string | null;
  location: string | null;
  facility: string | null;
  host_gym: string | null;
  state: string | null;
  start_date: string | null;
  end_date: string | null;
}

/** GET /api/meets — meets may be filtered by `state` query; `states` is always all distinct states in the qualifying set. */
export interface MeetsListResponse {
  meets: MeetSummary[];
  states: string[];
}

export interface MeetSessionSummary {
  session_id: string;
  label: string;
}

export type EventKey = "aa" | "vt" | "ub" | "bb" | "fx";

export const EVENTS: { key: EventKey; label: string }[] = [
  { key: "vt", label: "VT" },
  { key: "ub", label: "UB" },
  { key: "bb", label: "BB" },
  { key: "fx", label: "FX" },
  { key: "aa", label: "AA" },
];
