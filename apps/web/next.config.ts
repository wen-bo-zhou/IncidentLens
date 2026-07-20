import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const target = process.env.API_PROXY_TARGET ?? "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${target}/api/:path*` },
      { source: "/health/:path*", destination: `${target}/health/:path*` },
    ];
  },
};

export default nextConfig;
