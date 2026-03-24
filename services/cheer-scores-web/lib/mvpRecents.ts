import type { MvpRecentItem } from "./mvpTypes";

const KEY = "cheer-mvp-recents";
const MAX = 6;

export function readMvpRecents(): MvpRecentItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as MvpRecentItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function sameRecent(a: MvpRecentItem, b: MvpRecentItem): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "meet" && b.kind === "meet") return a.meetKey === b.meetKey;
  if (a.kind === "team" && b.kind === "team") return a.teamId === b.teamId;
  return false;
}

export function pushMvpRecent(item: MvpRecentItem): void {
  if (typeof window === "undefined") return;
  const cur = readMvpRecents().filter((x) => !sameRecent(x, item));
  cur.unshift(item);
  window.localStorage.setItem(KEY, JSON.stringify(cur.slice(0, MAX)));
}
