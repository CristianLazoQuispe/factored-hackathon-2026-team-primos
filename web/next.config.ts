import type { NextConfig } from "next";

// Static export: nginx serves `out/` (web/Dockerfile); the API is another service.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
