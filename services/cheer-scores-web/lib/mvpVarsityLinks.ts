const VARSITY_TV_ORIGIN = "https://tv.varsity.com";

/** Varsity MVP meets use ``VARSITY-<event_id>`` (see ingest ``varsity_client``). */
export function parseVarsityEventIdFromMeetKey(meetKey: string): number | null {
  const m = /^VARSITY-(\d+)$/.exec(meetKey.trim());
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) ? n : null;
}

/**
 * Public schedule hub on Varsity TV. Numeric path works (redirects/canonicalize like slug URLs).
 */
export function varsityOfficialScheduleUrlForMeetKey(meetKey: string): string | null {
  const id = parseVarsityEventIdFromMeetKey(meetKey);
  if (id == null) return null;
  return `${VARSITY_TV_ORIGIN}/events/${id}/schedule`;
}
