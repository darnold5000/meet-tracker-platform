import type { ScoresResponse } from "./types";

const getBaseUrl = () => {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) throw new Error("NEXT_PUBLIC_API_URL is not set");
  return url.replace(/\/$/, "");
};

export async function fetchScores(
  meetKey: string,
  params: { level?: string; division?: string; q?: string; limit?: number } = {}
): Promise<ScoresResponse> {
  const base = getBaseUrl();
  const search = new URLSearchParams();
  if (params.level && params.level !== "All") search.set("level", params.level);
  if (params.division && params.division !== "All") search.set("division", params.division);
  if (params.q) search.set("q", params.q);
  if (params.limit) search.set("limit", String(params.limit));

  const url = `${base}/api/meet/${encodeURIComponent(meetKey)}/scores${search.toString() ? `?${search}` : ""}`;
  const res = await fetch(url, { next: { revalidate: 0 } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Failed to fetch scores");
  }
  return res.json();
}
