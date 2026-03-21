import type { EventKey, ScoreRow } from "@/lib/types";

export function scoreRowKey(r: ScoreRow): string {
  return [r.athlete, r.gym, r.session ?? "", r.level, r.division].join("|");
}

/**
 * Competition-style ranks per event (1,1,3 for ties), using only the current filtered row set.
 * Used when API `place` is null (e.g. live / incomplete) so we still show current standing by score.
 */
export function computePerEventRanks(rows: ScoreRow[]): Map<string, Partial<Record<EventKey, number>>> {
  const map = new Map<string, Partial<Record<EventKey, number>>>();
  const events: EventKey[] = ["vt", "ub", "bb", "fx", "aa"];

  for (const ev of events) {
    const sorted = [...rows].sort((a, b) => {
      const sa = a[ev].score;
      const sb = b[ev].score;
      if (sa == null && sb == null) return a.athlete.localeCompare(b.athlete);
      if (sa == null) return 1;
      if (sb == null) return -1;
      if (sb !== sa) return sb - sa;
      return a.athlete.localeCompare(b.athlete);
    });

    let i = 0;
    let displayRank = 1;
    while (i < sorted.length) {
      const sc = sorted[i][ev].score;
      if (sc == null) {
        i++;
        continue;
      }
      let j = i + 1;
      while (j < sorted.length && sorted[j][ev].score === sc) j++;
      for (let k = i; k < j; k++) {
        const key = scoreRowKey(sorted[k]);
        const cur = map.get(key) ?? {};
        cur[ev] = displayRank;
        map.set(key, cur);
      }
      displayRank += j - i;
      i = j;
    }
  }

  return map;
}
