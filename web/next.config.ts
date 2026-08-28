import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "127.0.0.1", port: "8000", pathname: "/api/v1/public/media/**" },
      { protocol: "http", hostname: "localhost", port: "8000", pathname: "/api/v1/public/media/**" },
      // Mock-data-only placeholder imagery (web/src/lib/content/mock.ts) --
      // never used by the real API adapter.
      { protocol: "https", hostname: "picsum.photos", pathname: "/**" },
    ],
  },
};

export default nextConfig;
