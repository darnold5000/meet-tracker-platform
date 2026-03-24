import type {
  MvpResultsResponse,
  MvpSearchResponse,
  MvpTimelineResponse,
} from "./mvpTypes";

const getBaseUrl = () => {
  const viaProxy = process.env.NEXT_PUBLIC_API_VIA_PROXY === "1";
  if (viaProxy) return "/api-proxy";
  const url = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!url) {
    throw new Error(
      "Set NEXT_PUBLIC_API_URL (e.g. http://127.0.0.1:8003) or NEXT_PUBLIC_API_VIA_PROXY=1 for local dev"
    );
  }
  return url.replace(/\/$/, "");
};

export async function mvpSearch(q: string): Promise<MvpSearchResponse> {
  const base = getBaseUrl();
  const sp = new URLSearchParams();
  if (q.trim()) sp.set("q", q.trim());
  const res = await fetch(`${base}/api/mvp/search?${sp.toString()}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Search failed");
  }
  return res.json();
}

export async function mvpTimeline(
  meetKey: string,
  sessionId?: number | null
): Promise<MvpTimelineResponse> {
  const base = getBaseUrl();
  const sp = new URLSearchParams();
  if (sessionId != null) sp.set("session_id", String(sessionId));
  const q = sp.toString();
  const res = await fetch(
    `${base}/api/mvp/meet/${encodeURIComponent(meetKey)}/timeline${q ? `?${q}` : ""}`,
    { cache: "no-store" }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Failed to load timeline");
  }
  return res.json();
}

export async function mvpResults(
  meetKey: string,
  sessionId?: number | null
): Promise<MvpResultsResponse> {
  const base = getBaseUrl();
  const sp = new URLSearchParams();
  if (sessionId != null) sp.set("session_id", String(sessionId));
  const q = sp.toString();
  const res = await fetch(
    `${base}/api/mvp/meet/${encodeURIComponent(meetKey)}/results${q ? `?${q}` : ""}`,
    { cache: "no-store" }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Failed to load results");
  }
  return res.json();
}
