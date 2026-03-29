"use client";

import { openTallyFeedback, TALLY_FEEDBACK_FORM_ID } from "@/lib/feedback";

/** Fixed bottom-right control — same pattern as MeetView (gym scores). */
export function MvpFeedbackFab() {
  if (!TALLY_FEEDBACK_FORM_ID) return null;
  return (
    <button
      type="button"
      onClick={() => openTallyFeedback()}
      title="Quick feedback — about a minute"
      className="fixed bottom-5 right-4 z-50 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-800 shadow-lg ring-1 ring-black/5 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-red-400"
      aria-label="Open feedback form (about a minute)"
    >
      💬 Feedback
    </button>
  );
}
