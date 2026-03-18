/** Response shape from FastAPI GET /api/meet/{meet_key}/scores */
export interface ScoreRow {
  athlete: string;
  gym: string;
  level: string;
  division: string;
  aa: { score: number | null; place: number | null };
  vt: { score: number | null; place: number | null };
  ub: { score: number | null; place: number | null };
  bb: { score: number | null; place: number | null };
  fx: { score: number | null; place: number | null };
}

export interface ScoresResponse {
  meet_key: string;
  latest: unknown;
  count: number;
  rows: ScoreRow[];
}

export type EventKey = "aa" | "vt" | "ub" | "bb" | "fx";

export const EVENTS: { key: EventKey; label: string }[] = [
  { key: "vt", label: "VT" },
  { key: "ub", label: "UB" },
  { key: "bb", label: "BB" },
  { key: "fx", label: "FX" },
  { key: "aa", label: "AA" },
];
