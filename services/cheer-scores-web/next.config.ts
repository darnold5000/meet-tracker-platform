import type { NextConfig } from "next";

/** Dev-only: browser → same-origin `/api-proxy/...` → FastAPI (avoids CORS). */
const cheerApiDevTarget = process.env.CHEER_API_DEV_PROXY_TARGET ?? "http://127.0.0.1:8003";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [
      {
        source: "/api-proxy/:path*",
        destination: `${cheerApiDevTarget.replace(/\/$/, "")}/:path*`,
      },
    ];
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
