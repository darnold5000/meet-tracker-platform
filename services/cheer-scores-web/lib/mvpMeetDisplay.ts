import type { MvpMeetHit, MvpMeetSummary } from "./mvpTypes";

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
  if (!meet?.start_date) {
    return { label: "Scores", tone: "live" };
  }

  const now = new Date();
  const start = parseMvpCalendarDate(meet.start_date) ?? new Date(meet.start_date);
  const end = meet.end_date ? parseMvpCalendarDate(meet.end_date) ?? new Date(meet.end_date) : start;

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
  meet: MvpMeetSummary | null | undefined
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
 * Label for `<select>` and lists. If ``name`` (and location/date) are empty—common when
 * DB rows were created without a title—the browser would otherwise show only ``value``
 * (e.g. ``VARSITY-14478875``).
 */
export function mvpMeetPickerLabel(m: MvpMeetHit): string {
  const name = humanizedMeetName(m.name);
  const loc = (m.location ?? "").trim();
  const when = formatMvpMeetWhen(m);
  const bits = [name || null, loc || null, when || null].filter(Boolean) as string[];
  if (bits.length > 0) {
    return bits.join(" · ");
  }
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
