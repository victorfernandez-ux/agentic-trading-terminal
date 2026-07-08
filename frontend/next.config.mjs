/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy API calls to the FastAPI backend. BACKEND_URL lets a LAN/mobile
  // deployment point somewhere other than the dev default.
  // BUILD-TIME ONLY: rewrites are compiled into routes-manifest.json by
  // `next build`; setting BACKEND_URL at `next start` has no effect —
  // rebuild after changing it. (Same for NEXT_PUBLIC_WS_BASE in Watchlist.)
  async rewrites() {
    const backend = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
