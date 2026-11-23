/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  async rewrites() {
    return [
      {
        source: "/api/backend/rag/:path*",
        destination: `${process.env.RAG_SERVICE_URL || "http://localhost:8516"}/api/v1/rag/:path*`,
      },
      {
        source: "/api/backend/auth/:path*",
        destination: `${process.env.AUTH_SERVICE_URL || "http://localhost:8512"}/api/v1/auth/:path*`,
      },
      {
        source: "/api/backend/admin/:path*",
        destination: `${process.env.ADMIN_SERVICE_URL || "http://localhost:8515"}/api/v1/admin/:path*`,
      },
    ];
  },
};

export default nextConfig;
