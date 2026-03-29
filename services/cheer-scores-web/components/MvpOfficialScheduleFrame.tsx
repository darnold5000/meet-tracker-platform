"use client";

import Link from "next/link";
import { varsityOfficialScheduleUrlForMeetKey } from "@/lib/mvpVarsityLinks";

export function MvpOfficialScheduleFrame({ meetKey }: { meetKey: string }) {
  const scheduleUrl = varsityOfficialScheduleUrlForMeetKey(meetKey);

  if (!scheduleUrl) {
    return (
      <div className="mx-auto max-w-lg px-4 pb-16 pt-6">
        <Link href="/" className="inline-block text-sm font-medium text-[var(--brand-bright)]">
          ← Home
        </Link>
        <p className="mt-6 text-sm text-slate-700">
          Varsity’s full web schedule isn’t linked for this competition (only Varsity TV events with a numeric id
          are supported here).
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col bg-slate-100">
      <header className="relative flex shrink-0 items-center justify-center border-b border-slate-200 bg-white px-3 py-3 shadow-sm">
        <Link
          href="/"
          className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-semibold text-sky-900 hover:text-sky-950"
        >
          ← Home
        </Link>
        <p className="text-center text-[10px] font-medium uppercase tracking-wide text-slate-500">
          Official Varsity schedule
        </p>
      </header>
      <iframe
        title="Varsity official schedule"
        src={scheduleUrl}
        className="min-h-0 w-full flex-1 border-0 bg-white"
        referrerPolicy="no-referrer-when-downgrade"
      />
    </div>
  );
}
