import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async redirects() {
    return [
      {
        source: '/:path*',
        has: [
          { type: 'host', value: 'www.meetscores.app' },
        ],
        destination: 'https://meetscores.app/:path*',
        permanent: true,
      },
      {
        source: '/:path*',
        has: [
          { type: 'host', value: 'meetscores.live' },
        ],
        destination: 'https://meetscores.app/:path*',
        permanent: true,
      },
      {
        source: '/:path*',
        has: [
          { type: 'host', value: 'www.meetscores.live' },
        ],
        destination: 'https://meetscores.app/:path*',
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
