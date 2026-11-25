import type { NextConfig } from "next";

// The browser only ever talks to this Next.js origin. /api/* is forwarded to FastAPI, so the
// session cookie (HttpOnly, SameSite=Lax) is first-party and no CORS setup is needed.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
