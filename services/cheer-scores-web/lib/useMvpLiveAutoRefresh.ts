"use client";

import { useEffect, useRef } from "react";
import { MVP_LIVE_REFRESH_INTERVAL_MS } from "./mvpLiveRefresh";

/**
 * Poll while the document is visible; refresh once when the tab becomes visible again.
 * Matches gym-scores `MeetView` live refresh behavior.
 */
export function useMvpLiveAutoRefresh(
  enabled: boolean,
  canRun: boolean,
  refresh: () => void | Promise<void>
) {
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  useEffect(() => {
    if (!enabled || !canRun) return;

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const run = () => {
      void refreshRef.current();
    };

    const start = () => {
      if (intervalId != null) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      intervalId = setInterval(run, MVP_LIVE_REFRESH_INTERVAL_MS);
    };

    const stop = () => {
      if (intervalId == null) return;
      clearInterval(intervalId);
      intervalId = null;
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        run();
        start();
      } else {
        stop();
      }
    };

    start();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [enabled, canRun]);
}
