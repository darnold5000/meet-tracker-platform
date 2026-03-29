import type { MetadataRoute } from "next";

/** Bust CDN + SW caches when replacing `public/icon-*.png` (keep in sync with `public/sw.js` ICON_QUERY). */
const ICON_Q = "?v=5";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Cheer Tracker",
    short_name: "Cheer Tracker",
    description: "Track live all-star cheer competition scores",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#00adef",
    icons: [
      {
        src: `/icon-192.png${ICON_Q}`,
        type: "image/png",
        sizes: "192x192",
      },
      {
        src: `/icon-512.png${ICON_Q}`,
        type: "image/png",
        sizes: "512x512",
      },
      {
        src: `/icon-1024.png${ICON_Q}`,
        type: "image/png",
        sizes: "1024x1024",
      },
    ],
  };
}
