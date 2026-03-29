"use client";

import { useCallback, useEffect, useState } from "react";

const LS_KEY = "cheer-mvp-about-banner-dismissed";

export function MvpAboutBanner() {
  const [ready, setReady] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    try {
      setDismissed(window.localStorage.getItem(LS_KEY) === "1");
    } catch {
      setDismissed(false);
    }
    setReady(true);
  }, []);

  const dismiss = useCallback(() => {
    try {
      window.localStorage.setItem(LS_KEY, "1");
    } catch {
      /* ignore */
    }
    setDismissed(true);
  }, []);

  if (!ready || dismissed) return null;

  return (
    <div className="mb-4 rounded-xl border border-sky-200/80 bg-sky-50/90 px-3 py-2.5 text-sm text-slate-800 shadow-sm ring-1 ring-sky-100">
      <div className="flex gap-2">
        <div className="min-w-0 flex-1 space-y-2">
          <p className="font-semibold text-slate-900">About this app</p>
          <p className="text-xs leading-relaxed text-slate-700">
            Choose a competition, then switch between <span className="font-medium">Results</span> and{" "}
            <span className="font-medium">Schedule</span>. Narrow the list with gym, category, and team filters.
          </p>
          <p className="text-xs leading-relaxed text-slate-700">
            In <span className="font-medium">Results</span>, open a team to see the other competitors in that
            division.
          </p>
          <p className="text-xs leading-relaxed text-slate-600">
            <span className="font-medium text-slate-800">Coming soon:</span> richer team pages, notifications
            for schedule and scoring updates, gym and team customization, and improvements from your feedback.
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="shrink-0 self-start rounded-lg px-2 py-1 text-xs font-medium text-sky-800 hover:bg-sky-100"
          aria-label="Dismiss about box"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
