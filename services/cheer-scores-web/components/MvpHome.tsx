"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { mvpSearch, mvpUpcomingMeets } from "@/lib/mvpApi";
import { formatMvpMeetWhen, humanizedMeetName, mvpMeetPickerLabel } from "@/lib/mvpMeetDisplay";
import type {
  MvpMeetHit,
  MvpRecentItem,
  MvpSearchResponse,
  MvpTeamHit,
  MvpUpcomingMeetsResponse,
} from "@/lib/mvpTypes";
import { pushMvpRecent, readMvpRecents } from "@/lib/mvpRecents";
import { MvpInstallHintBanner } from "@/components/MvpPwaInstallProvider";

export function MvpHome() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [data, setData] = useState<MvpSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [recents, setRecents] = useState<MvpRecentItem[]>([]);
  const [upcoming, setUpcoming] = useState<MvpUpcomingMeetsResponse | null>(null);

  useEffect(() => {
    setRecents(readMvpRecents());
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 280);
    return () => clearTimeout(t);
  }, [q]);

  const runSearch = useCallback(async (query: string) => {
    setLoading(true);
    setErr(null);
    try {
      const res = await mvpSearch(query);
      setData(res);
    } catch (e) {
      setData(null);
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void runSearch(debounced);
  }, [debounced, runSearch]);

  useEffect(() => {
    if (debounced.trim()) {
      setUpcoming(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const u = await mvpUpcomingMeets(3);
        if (!cancelled) setUpcoming(u);
      } catch {
        if (!cancelled) setUpcoming(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const onOpenMeet = (m: MvpMeetHit) => {
    pushMvpRecent({ kind: "meet", meetKey: m.meet_key, label: mvpMeetPickerLabel(m) });
    setRecents(readMvpRecents());
  };

  const onPeekTeam = (t: MvpTeamHit) => {
    pushMvpRecent({ kind: "team", teamId: t.id, label: t.name });
    setRecents(readMvpRecents());
  };

  return (
    <div className="mx-auto max-w-lg px-4 pb-16 pt-8">
      <Link
        href="/"
        className="mb-4 inline-block text-sm font-medium text-[var(--brand-bright)]"
      >
        ← Competition view
      </Link>
      <header className="mb-6 rounded-2xl bg-gradient-to-br from-[var(--brand)] via-[#003d52] to-[var(--brand-bright)] px-4 py-4 text-white shadow-lg">
        <h1 className="text-lg font-bold tracking-tight">Cheer Tracker</h1>
        <p className="mt-1 text-sm opacity-90">Search teams or competitions</p>
      </header>

      <MvpInstallHintBanner tightTop />

      <label className="sr-only" htmlFor="mvp-search">
        Search
      </label>
      <input
        id="mvp-search"
        type="search"
        placeholder="Try “Tiny Twisters”, “Atlanta”, or JPAC…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="mb-4 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-[var(--text)] shadow-sm outline-none ring-[var(--brand)] placeholder:text-slate-400 focus:ring-2"
        autoComplete="off"
      />

      {loading && <p className="mb-3 text-sm text-[var(--muted)]">Searching…</p>}
      {err && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{err}</p>}

      {!debounced.trim() && upcoming && upcoming.meets.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Up next
          </h2>
          <p className="mb-2 text-[11px] leading-snug text-slate-500">
            Next competitions on the calendar (rebroadcasts excluded).
          </p>
          <ul className="space-y-2">
            {upcoming.meets.map((m) => (
              <li key={m.meet_key}>
                <Link
                  href={`/meet/${encodeURIComponent(m.meet_key)}`}
                  onClick={() => onOpenMeet(m)}
                  className="block rounded-xl border border-sky-200/80 bg-sky-50/80 p-3 shadow-sm transition hover:border-[var(--brand)]"
                >
                  <div className="font-semibold text-[var(--text)]">
                    {humanizedMeetName(m.name) || m.meet_key}
                  </div>
                  <div className="mt-0.5 text-xs text-[var(--muted)]">
                    {[m.location, formatMvpMeetWhen(m)].filter(Boolean).join(" · ")}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {recents.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Recent</h2>
          <ul className="space-y-1">
            {recents.map((r, i) => (
              <li key={`${r.kind}-${i}`}>
                {r.kind === "meet" ? (
                  <Link
                    href={`/meet/${encodeURIComponent(r.meetKey)}`}
                    className="block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-[var(--brand)] shadow-sm"
                  >
                    {r.label}
                  </Link>
                ) : (
                  <span className="block rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-sm text-[var(--muted)]">
                    Team: {r.label}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {data && (
        <>
          <section className="mb-6">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Competitions</h2>
            {data.meets.length === 0 ? (
              <p className="text-sm text-[var(--muted)]">No meets match.</p>
            ) : (
              <ul className="space-y-2">
                {data.meets.map((m) => (
                  <li key={m.meet_key}>
                    <Link
                      href={`/meet/${encodeURIComponent(m.meet_key)}`}
                      onClick={() => onOpenMeet(m)}
                      className="block rounded-xl border border-slate-200 bg-white p-3 shadow-sm transition hover:border-[var(--brand)]"
                    >
                      <div className="font-semibold text-[var(--text)]">
                        {humanizedMeetName(m.name) || m.meet_key}
                      </div>
                      <div className="mt-0.5 text-xs text-[var(--muted)]">
                        {[m.location, formatMvpMeetWhen(m)].filter(Boolean).join(" · ")}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Teams</h2>
            {data.teams.length === 0 ? (
              <p className="text-sm text-[var(--muted)]">No teams match.</p>
            ) : (
              <ul className="space-y-2">
                {data.teams.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => onPeekTeam(t)}
                      className="w-full rounded-xl border border-slate-200 bg-white p-3 text-left shadow-sm"
                    >
                      <div className="font-semibold text-[var(--text)]">{t.name}</div>
                      <div className="mt-0.5 text-xs text-[var(--muted)]">
                        {[t.gym_name, t.level, t.division].filter(Boolean).join(" · ")}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
