/** Defaults for Varsity MVP meet; override with NEXT_PUBLIC_* .
 *  Rows come from ingest (`event-hub/…/results`). If Flo returns “Results not found” for
 *  this numeric id, timeline/results stay empty even when the Varsity schedule lists the event. */
export const MVP_DEFAULT_MEET_KEY = (
  process.env.NEXT_PUBLIC_DEFAULT_MVP_MEET_KEY ??
  process.env.NEXT_PUBLIC_DEFAULT_MEET_KEY ??
  "VARSITY-14478900"
).trim();

export const MVP_DEFAULT_MEET_LABEL = (
  process.env.NEXT_PUBLIC_DEFAULT_MVP_MEET_LABEL ??
  process.env.NEXT_PUBLIC_DEFAULT_MEET_LABEL ??
  "One Up Grand Nationals"
).trim();

/** Default gym filter on the MVP dashboard (case-insensitive exact match against ``team_gym_name``). */
export const MVP_DEFAULT_GYM_FILTER = (
  process.env.NEXT_PUBLIC_DEFAULT_MVP_GYM ?? "All"
).trim();
