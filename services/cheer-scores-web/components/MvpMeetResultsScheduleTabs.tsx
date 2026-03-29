"use client";

import Link from "next/link";
import { varsityOfficialScheduleUrlForMeetKey } from "@/lib/mvpVarsityLinks";

const pillBase =
  "flex-1 rounded-full py-1.5 text-[11px] font-semibold uppercase tracking-wide transition-all duration-200";
const pillActive = "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200";
const pillInactive = "text-slate-600";

export type MvpMeetTab = "results" | "timeline";

type Props = {
  meetKey: string;
  tab: MvpMeetTab;
  onTabChange: (t: MvpMeetTab) => void;
  /** Live/upcoming meets: show in-app mat-order tab when there is no Varsity TV id. */
  showInAppTimelineTab: boolean;
};

/** Results vs Schedule: for Varsity TV meets, Schedule navigates in-app to the embedded official schedule page. */
export function MvpMeetResultsScheduleTabs({
  meetKey,
  tab,
  onTabChange,
  showInAppTimelineTab,
}: Props) {
  const varsityScheduleUrl = varsityOfficialScheduleUrlForMeetKey(meetKey);
  const scheduleOpensVarsity = varsityScheduleUrl != null;
  if (!showInAppTimelineTab && !scheduleOpensVarsity) return null;

  return (
    <div className="flex gap-1 p-1">
      <button
        type="button"
        onClick={() => onTabChange("results")}
        className={`${pillBase} ${tab === "results" ? pillActive : pillInactive}`}
      >
        Results
      </button>
      {scheduleOpensVarsity ? (
        <Link
          href={`/meet/${encodeURIComponent(meetKey)}/official-schedule`}
          className={`${pillBase} ${pillInactive} text-center hover:text-slate-900`}
          aria-label="Official Varsity schedule"
        >
          Schedule
        </Link>
      ) : (
        <button
          type="button"
          onClick={() => onTabChange("timeline")}
          className={`${pillBase} ${tab === "timeline" ? pillActive : pillInactive}`}
        >
          Schedule
        </button>
      )}
    </div>
  );
}
