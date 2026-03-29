import type { MvpMeetHit, MvpMeetSummary, MvpResultRow, MvpTimelineItem } from "./mvpTypes";
import { MVP_DEFAULT_MEET_KEY } from "./mvpDefaults";

function mvpDefaultConfiguredMeetVenueLine(): string | null {
  const raw = (
    process.env.NEXT_PUBLIC_DEFAULT_MVP_MEET_LOCATION ??
    process.env.NEXT_PUBLIC_DEFAULT_MEET_LOCATION ??
    ""
  ).trim();
  return raw || null;
}

/**
 * First non-empty trimmed location among candidates; optional env fallback for the default meet key.
 */
export function mvpCoalesceMeetLocation(
  meetKey: string,
  ...candidates: (string | null | undefined)[]
): string | null {
  for (const c of candidates) {
    const t = (c ?? "").trim();
    if (t) return t;
  }
  if (meetKey === MVP_DEFAULT_MEET_KEY) {
    return mvpDefaultConfiguredMeetVenueLine();
  }
  return null;
}

/** Placeholder title written by ingest before real event name exists. */
export const GENERIC_VARSITY_EVENT_NAME = /^varsity\s+event\s+\d+$/i;

/** Parse API date-only strings as local calendar dates (avoid UTC shift from `new Date("2026-03-20")`). */
export function parseMvpCalendarDate(value: string | null | undefined): Date | null {
  if (!value || typeof value !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mon = Number(m[2]) - 1;
  const d = Number(m[3]);
  if (!Number.isFinite(y) || !Number.isFinite(mon) || !Number.isFinite(d)) return null;
  return new Date(y, mon, d);
}

/**
 * Meet schedule badge (same idea as gym `MeetView`): show LIVE or upcoming start; hide when the meet is in the past.
 */
export function getMvpMeetScheduleStatus(
  meet: MvpMeetSummary | null | undefined
): { label: string; tone: "live" | "upcoming" | "past" } {
  if (!meet?.start_date && !meet?.starts_at) {
    return { label: "Scores", tone: "live" };
  }

  const now = new Date();
  if (meet.starts_at) {
    const startsAt = new Date(meet.starts_at);
    if (!Number.isNaN(startsAt.getTime()) && now < startsAt) {
      const tf = new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
      return { label: `Starts ${tf.format(startsAt)}`, tone: "upcoming" };
    }
  }

  const start = meet.start_date
    ? parseMvpCalendarDate(meet.start_date) ?? new Date(meet.start_date)
    : meet.starts_at
      ? new Date(meet.starts_at)
      : now;
  const end = meet.end_date
    ? parseMvpCalendarDate(meet.end_date) ?? new Date(meet.end_date)
    : meet.ends_at
      ? new Date(meet.ends_at)
      : start;

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const endDay = new Date(end.getFullYear(), end.getMonth(), end.getDate());

  const fmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
  const rangeLabel =
    fmt.format(startDay) + (endDay.getTime() !== startDay.getTime() ? `–${fmt.format(endDay)}` : "");

  if (today >= startDay && today <= endDay) {
    return { label: "LIVE", tone: "live" };
  }
  if (today < startDay) {
    return { label: `Starts ${fmt.format(startDay)}`, tone: "upcoming" };
  }
  return { label: rangeLabel, tone: "past" };
}

export type MvpMeetPickerTimeBucket = "upcoming" | "recent" | "past";

/** Days after the last day of a meet that it still appears under Recent in the meet picker. */
export const MVP_MEET_PICKER_RECENT_GRACE_DAYS = 30;

function mvpStartOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/**
 * Buckets for the MVP meet dropdown: upcoming (not started), recent (in progress or ended within grace),
 * past (older).
 */
export function getMvpMeetHitPickerBucket(
  m: MvpMeetHit,
  now: Date = new Date()
): MvpMeetPickerTimeBucket {
  const today = mvpStartOfLocalDay(now);
  const msDay = 86_400_000;

  if (m.starts_at) {
    const startsAt = new Date(m.starts_at);
    if (!Number.isNaN(startsAt.getTime())) {
      const sd = mvpStartOfLocalDay(startsAt);
      if (today.getTime() < sd.getTime()) return "upcoming";
    }
  }

  const start = m.start_date
    ? parseMvpCalendarDate(m.start_date) ?? new Date(m.start_date)
    : m.starts_at
      ? new Date(m.starts_at)
      : null;

  if (!start || Number.isNaN(start.getTime())) {
    return "recent";
  }

  const startDay = mvpStartOfLocalDay(start);

  const endSrc = m.end_date
    ? parseMvpCalendarDate(m.end_date) ?? new Date(m.end_date)
    : m.ends_at
      ? new Date(m.ends_at)
      : start;
  let endDay = mvpStartOfLocalDay(
    !endSrc || Number.isNaN(endSrc.getTime()) ? start : endSrc
  );
  if (endDay.getTime() < startDay.getTime()) endDay = startDay;

  if (today.getTime() < startDay.getTime()) return "upcoming";
  if (today.getTime() <= endDay.getTime()) return "recent";

  const daysSinceEnd = Math.floor((today.getTime() - endDay.getTime()) / msDay);
  if (daysSinceEnd <= MVP_MEET_PICKER_RECENT_GRACE_DAYS) return "recent";
  return "past";
}

/**
 * Order-of-performance (timeline) tab: show for live and upcoming meets.
 * Past meets → surface results only (`tone === "past"`).
 * When ``meet`` is still loading (null/undefined), return true so both tabs stay available until dates are known.
 */
export function mvpMeetShowsTimelineTab(meet: MvpMeetSummary | null | undefined): boolean {
  if (!meet) return true;
  return getMvpMeetScheduleStatus(meet).tone !== "past";
}

/**
 * Readable date range for the header footer (start through end, inclusive).
 */
export function formatMvpMeetDateRangeReadable(
  meet: Pick<MvpMeetSummary, "start_date" | "end_date"> | null | undefined
): string | null {
  if (!meet?.start_date) return null;

  const start = parseMvpCalendarDate(meet.start_date) ?? new Date(meet.start_date);
  const end = meet.end_date ? parseMvpCalendarDate(meet.end_date) ?? new Date(meet.end_date) : start;

  const sameCalendarDay =
    start.getFullYear() === end.getFullYear() &&
    start.getMonth() === end.getMonth() &&
    start.getDate() === end.getDate();

  const longDate: Intl.DateTimeFormatOptions = {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  };

  if (sameCalendarDay) {
    return start.toLocaleDateString("en-US", longDate);
  }

  const y1 = start.getFullYear();
  const y2 = end.getFullYear();
  const sameYear = y1 === y2;
  const sameMonth = sameYear && start.getMonth() === end.getMonth();

  if (sameMonth) {
    const month = start.toLocaleDateString("en-US", { month: "long" });
    return `${month} ${start.getDate()}–${end.getDate()}, ${y1}`;
  }
  if (sameYear) {
    const a = start.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const b = end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    return `${a} – ${b}`;
  }
  const a = start.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const b = end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return `${a} – ${b}`;
}

/** User-facing “when does this start?” for empty timeline / pre-event messaging. */
export function formatMvpMeetStartsAtReadable(
  meet: Pick<MvpMeetSummary, "starts_at" | "start_date"> | null | undefined
): string | null {
  if (meet?.starts_at) {
    const d = new Date(meet.starts_at);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      });
    }
  }
  if (meet?.start_date) {
    const d = parseMvpCalendarDate(meet.start_date) ?? new Date(meet.start_date);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      });
    }
  }
  return null;
}

export function humanizedMeetName(name: string | null | undefined): string {
  const t = (name ?? "").trim();
  if (!t || GENERIC_VARSITY_EVENT_NAME.test(t)) {
    return "";
  }
  return t;
}

/** Single-line date for meet cards / dropdowns (local calendar day). */
export function formatMvpMeetWhen(m: MvpMeetHit): string {
  if (!m.start_date) return "";
  try {
    const d = new Date(m.start_date + "T12:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return m.start_date;
  }
}

export function mvpMeetSummaryToHit(meet: MvpMeetSummary): MvpMeetHit {
  return {
    meet_key: meet.meet_key,
    name: meet.name,
    location: meet.location,
    start_date: meet.start_date,
    end_date: meet.end_date,
  };
}

/**
 * Short label for `<select>` options, recents, etc.: meet name only (no location/date).
 * Falls back to ``meet_key`` when there is no displayable title.
 */
export function mvpMeetPickerLabel(m: MvpMeetHit): string {
  const name = humanizedMeetName(m.name);
  if (name) return name;
  return m.meet_key;
}

/** Page header: never show "Varsity event 123" when we have a configured default label. */
export function mvpMeetHeaderTitle(
  meet: MvpMeetSummary | undefined,
  activeMeetKey: string,
  defaultMeetKey: string,
  defaultMeetLabel: string
): string {
  if (meet) {
    const fromPicker = mvpMeetPickerLabel(mvpMeetSummaryToHit(meet));
    if (fromPicker !== meet.meet_key) {
      return fromPicker;
    }
    if (meet.meet_key === defaultMeetKey) {
      return defaultMeetLabel;
    }
    return meet.meet_key;
  }
  return activeMeetKey === defaultMeetKey ? defaultMeetLabel : activeMeetKey;
}

/**
 * Header title line: meet name only (no date/location). Avoids duplicating dates shown in the footer row.
 */
export function mvpMeetHeaderNameLine(
  meet: MvpMeetSummary | undefined,
  activeMeetKey: string,
  defaultMeetKey: string,
  defaultMeetLabel: string
): string {
  if (meet) {
    const name = humanizedMeetName(meet.name);
    if (name) return name;
    if (meet.meet_key === defaultMeetKey) return defaultMeetLabel;
    return meet.meet_key;
  }
  return activeMeetKey === defaultMeetKey ? defaultMeetLabel : activeMeetKey;
}

function formatMvpClockTimeShort(iso: string | null | undefined): string {
  if (!iso?.trim()) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

/**
 * Schedule-tab time column: wall-clock when the feed has it.
 * Varsity results ingest often leaves both null — then show an em dash (not a bug).
 */
export function mvpTimelineWhenDisplay(
  row: Pick<MvpTimelineItem, "scheduled_time" | "actual_time">
): { text: string; title: string } {
  const sched = row.scheduled_time?.trim() ? formatMvpClockTimeShort(row.scheduled_time) : "";
  if (sched) return { text: sched, title: "Scheduled time" };
  const act = row.actual_time?.trim() ? formatMvpClockTimeShort(row.actual_time) : "";
  if (act) return { text: act, title: "Actual time (no scheduled time in feed)" };
  return {
    text: "—",
    title:
      "No time in feed yet. List order is session + performance order from Varsity (not sorted by clock or by done vs upcoming).",
  };
}

/** When ingest has performance times, surface them on result cards (Schedule tab still has full order). */
export function mvpResultRowScheduleCaption(
  r: Pick<MvpResultRow, "scheduled_time" | "actual_time">
): string | null {
  const perf = r.actual_time?.trim() ? formatMvpClockTimeShort(r.actual_time) : "";
  if (perf) return `Performed ${perf}`;
  const sched = r.scheduled_time?.trim() ? formatMvpClockTimeShort(r.scheduled_time) : "";
  if (sched) return `Scheduled ${sched}`;
  return null;
}
