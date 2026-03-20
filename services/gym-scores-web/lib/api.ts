import type { ScoresResponse, MeetSummary, MeetSessionSummary } from "./types";

const getBaseUrl = () => {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) throw new Error("NEXT_PUBLIC_API_URL is not set");
  return url.replace(/\/$/, "");
};

export async function fetchScores(
  meetKey: string,
  params: {
    level?: string;
    division?: string;
    gym?: string;
    session?: string;
    athlete?: string;
    q?: string;
    limit?: number;
  } = {}
): Promise<ScoresResponse> {
  const base = getBaseUrl();
  const search = new URLSearchParams();
  if (params.level && params.level !== "All") search.set("level", params.level);
  if (params.division && params.division !== "All") search.set("division", params.division);
  if (params.gym && params.gym !== "All") search.set("gym", params.gym);
  if (params.session && params.session !== "All") search.set("session", params.session);
  if (params.athlete && params.athlete !== "All") search.set("athlete", params.athlete);
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

export async function fetchMeets(): Promise<MeetSummary[]> {
  const base = getBaseUrl();
  const res = await fetch(`${base}/api/meets`, { next: { revalidate: 0 } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Failed to fetch meets");
  }
  const body = (await res.json()) as { meets?: MeetSummary[] };
  return body.meets ?? [];
}

export async function fetchMeetSessions(meetKey: string): Promise<MeetSessionSummary[]> {
  const base = getBaseUrl();
  const res = await fetch(`${base}/api/meet/${encodeURIComponent(meetKey)}/sessions`, {
    next: { revalidate: 0 },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Failed to fetch sessions");
  }
  const body = (await res.json()) as { sessions?: MeetSessionSummary[] };
  return body.sessions ?? [];
}

export async function fetchMeetAthletes(
  meetKey: string,
  params: { level?: string; division?: string; gym?: string; session?: string } = {}
): Promise<string[]> {
  const base = getBaseUrl();
  const search = new URLSearchParams();

  if (params.level && params.level !== "All") search.set("level", params.level);
  if (params.division && params.division !== "All") search.set("division", params.division);
  if (params.gym && params.gym !== "All") search.set("gym", params.gym);
  if (params.session && params.session !== "All") search.set("session", params.session);

  const url = `${base}/api/meet/${encodeURIComponent(meetKey)}/athletes${
    search.toString() ? `?${search}` : ""
  }`;
  const res = await fetch(url, { next: { revalidate: 0 } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Failed to fetch athletes");
  }
  const body = (await res.json()) as { athletes?: string[] };
  return body.athletes ?? [];
}
