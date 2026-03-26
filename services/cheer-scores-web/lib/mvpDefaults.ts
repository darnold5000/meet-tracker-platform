/** Defaults for Varsity MVP meet (CHEERSPORT Atlanta); override with NEXT_PUBLIC_* . */
export const MVP_DEFAULT_MEET_KEY = (
  process.env.NEXT_PUBLIC_DEFAULT_MVP_MEET_KEY ??
  process.env.NEXT_PUBLIC_DEFAULT_MEET_KEY ??
  "VARSITY-14478875"
).trim();

export const MVP_DEFAULT_MEET_LABEL = (
  process.env.NEXT_PUBLIC_DEFAULT_MVP_MEET_LABEL ??
  process.env.NEXT_PUBLIC_DEFAULT_MEET_LABEL ??
  "2026 CHEERSPORT National All Star Cheerleading Championship"
).trim();
