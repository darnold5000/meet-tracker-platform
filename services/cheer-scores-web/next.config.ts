import type { NextConfig } from "next";

/** Local dev default when using `/api-proxy` (see NEXT_PUBLIC_API_VIA_PROXY). */
const cheerApiDevTarget = process.env.CHEER_API_DEV_PROXY_TARGET ?? "http://127.0.0.1:8003";

/** Production: set on the host (Vercel/Cloud Run) — not NEXT_PUBLIC_. Used when NEXT_PUBLIC_API_VIA_PROXY=1. */
const cheerApiProdProxyTarget = (process.env.CHEER_SCORES_API_PROXY_TARGET ?? "").trim().replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (process.env.NODE_ENV === "development") {
      return [
        {
          source: "/api-proxy/:path*",
          destination: `${cheerApiDevTarget.replace(/\/$/, "")}/:path*`,
        },
      ];
    }
    if (process.env.NEXT_PUBLIC_API_VIA_PROXY === "1" && cheerApiProdProxyTarget) {
      return [
        {
          source: "/api-proxy/:path*",
          destination: `${cheerApiProdProxyTarget}/:path*`,
        },
      ];
    }
    return [];
  },
  async redirects() {
    return [
      // Add host → canonical URL redirects for your cheer domain here, e.g.:
      // {
      //   source: "/:path*",
      //   has: [{ type: "host", value: "www.cheer.example" }],
      //   destination: "https://cheer.example/:path*",
      //   permanent: true,
      // },
    ];
  },
};

export default nextConfig;
