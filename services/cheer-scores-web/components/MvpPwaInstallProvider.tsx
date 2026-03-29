"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const LS_INSTALLED = "cheer-mvp-installed";
const LS_A2HS_BROWSER_HINT = "cheer-mvp-a2hs-browser-hint-dismissed";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

function isIosLikeDevice(): boolean {
  if (typeof window === "undefined") return false;
  const ua = navigator.userAgent;
  if (/iPad|iPhone|iPod/i.test(ua)) return true;
  return navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
}

function isAndroidChrome(): boolean {
  if (typeof window === "undefined") return false;
  const ua = navigator.userAgent;
  return /Android/i.test(ua) && /Chrome/i.test(ua) && !/Edg/i.test(ua);
}

type PwaInstallContextValue = {
  clientInstallMetaReady: boolean;
  deferredInstallPrompt: BeforeInstallPromptEvent | null;
  isIosLike: boolean;
  isAndroidChromeUa: boolean;
  isStandalone: boolean;
  hideInstallHint: boolean;
  onInstallClick: () => Promise<void>;
};

const PwaInstallContext = createContext<PwaInstallContextValue | null>(null);

export function useMvpPwaInstall(): PwaInstallContextValue | null {
  return useContext(PwaInstallContext);
}

export function MvpPwaInstallProvider({ children }: { children: ReactNode }) {
  const [deferredInstallPrompt, setDeferredInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isIosLike, setIsIosLike] = useState(false);
  const [isAndroidChromeUa, setIsAndroidChromeUa] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);
  const [hideInstallHint, setHideInstallHint] = useState(false);
  const [clientInstallMetaReady, setClientInstallMetaReady] = useState(false);

  useEffect(() => {
    const nav = window.navigator as Navigator & { standalone?: boolean };
    const iosLike = isIosLikeDevice();
    setIsAndroidChromeUa(isAndroidChrome());
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches || Boolean(nav.standalone);
    const previouslyInstalled = window.localStorage.getItem(LS_INSTALLED) === "1";
    setIsIosLike(iosLike);
    setIsStandalone(standalone);
    setHideInstallHint(previouslyInstalled || standalone);

    const swOn =
      process.env.NODE_ENV === "production" || process.env.NEXT_PUBLIC_PWA_IN_DEV === "1";

    if ("serviceWorker" in nav) {
      if (swOn) {
        void nav.serviceWorker.register("/sw.js");
      } else {
        void nav.serviceWorker.getRegistrations().then((regs) => {
          regs.forEach((reg) => void reg.unregister());
        });
        if ("caches" in window) {
          void caches.keys().then((keys) => {
            keys.forEach((key) => void caches.delete(key));
          });
        }
      }
    }

    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setDeferredInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const onInstalled = () => {
      setDeferredInstallPrompt(null);
      setIsStandalone(true);
      setHideInstallHint(true);
      window.localStorage.setItem(LS_INSTALLED, "1");
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onInstalled);
    setClientInstallMetaReady(true);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const onInstallClick = useCallback(async () => {
    if (!deferredInstallPrompt) return;
    await deferredInstallPrompt.prompt();
    setDeferredInstallPrompt(null);
  }, [deferredInstallPrompt]);

  const value = useMemo(
    () => ({
      clientInstallMetaReady,
      deferredInstallPrompt,
      isIosLike,
      isAndroidChromeUa,
      isStandalone,
      hideInstallHint,
      onInstallClick,
    }),
    [
      clientInstallMetaReady,
      deferredInstallPrompt,
      isIosLike,
      isAndroidChromeUa,
      isStandalone,
      hideInstallHint,
      onInstallClick,
    ],
  );

  return <PwaInstallContext.Provider value={value}>{children}</PwaInstallContext.Provider>;
}

type InstallBannerProps = {
  /** Use when the banner sits right under a header that already has bottom margin (avoids double gap). */
  tightTop?: boolean;
};

/** Place below the page header (not in root layout) so it matches gym scores ordering. */
export function MvpInstallHintBanner({ tightTop = false }: InstallBannerProps) {
  const ctx = useMvpPwaInstall();
  const [genericBrowserHintDismissed, setGenericBrowserHintDismissed] = useState(false);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(LS_A2HS_BROWSER_HINT) === "1") {
        setGenericBrowserHintDismissed(true);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const dismissGenericBrowserHint = useCallback(() => {
    try {
      window.localStorage.setItem(LS_A2HS_BROWSER_HINT, "1");
    } catch {
      /* ignore */
    }
    setGenericBrowserHintDismissed(true);
  }, []);

  if (!ctx) return null;
  const {
    clientInstallMetaReady,
    deferredInstallPrompt,
    isIosLike,
    isAndroidChromeUa,
    isStandalone,
    hideInstallHint,
    onInstallClick,
  } = ctx;
  if (!clientInstallMetaReady || isStandalone || hideInstallHint) return null;

  const isGenericDesktopHint =
    !deferredInstallPrompt && !isIosLike && !isAndroidChromeUa;
  if (isGenericDesktopHint && genericBrowserHintDismissed) return null;

  return (
    <div className={`mb-2 rounded-xl bg-white p-3 shadow-sm ${tightTop ? "mt-0" : "mt-4"}`}>
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-700">
        {deferredInstallPrompt ? (
          <div className="flex items-center justify-between gap-2">
            <span>Install this app on your home screen for quick access.</span>
            <button
              type="button"
              onClick={() => void onInstallClick()}
              className="shrink-0 rounded-full bg-red-600 px-3 py-1.5 text-xs font-semibold text-white"
            >
              Add app
            </button>
          </div>
        ) : isIosLike ? (
          <div className="space-y-1">
            <p className="font-semibold text-slate-900">Install on iPhone (2 quick steps):</p>
            <p>
              1) Tap the Share button{" "}
              <span
                aria-hidden="true"
                className="inline-flex items-center rounded border border-slate-300 bg-white px-1.5 py-0.5 align-middle font-semibold"
              >
                <svg viewBox="0 0 20 20" className="mr-1 h-3.5 w-3.5" fill="none">
                  <path
                    d="M10 13V3m0 0L6.5 6.5M10 3l3.5 3.5M4 10.5V15a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-4.5"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                Share
              </span>
            </p>
            <p>
              2) Scroll down and tap <strong>Add to Home Screen</strong>.
            </p>
          </div>
        ) : isAndroidChromeUa ? (
          <div className="space-y-1">
            <p className="font-semibold text-slate-900">Install on Android (Chrome)</p>
            <p>
              Tap <strong>⋮</strong> (menu) → <strong>Install app</strong> or{" "}
              <strong>Add to Home screen</strong>. If you don’t see it, try the same from the browser menu.
            </p>
          </div>
        ) : (
          <div className="relative pr-7">
            <button
              type="button"
              onClick={() => dismissGenericBrowserHint()}
              className="absolute right-0 top-0 flex h-7 w-7 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200/80 hover:text-slate-800"
              aria-label="Dismiss"
            >
              <span className="text-lg leading-none" aria-hidden="true">
                ×
              </span>
            </button>
            <p className="leading-snug text-slate-700">
              <span className="font-semibold text-slate-900">Add to home screen:</span> look for an install icon in
              the address bar, or open the browser menu and choose <strong>Install</strong> /{" "}
              <strong>Add to Home screen</strong>.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
