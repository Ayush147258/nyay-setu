import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Enable React strict mode for better dev-time warnings
  reactStrictMode: true,

  // Image domains for avatars (Google OAuth profile images)
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
      { protocol: "https", hostname: "avatars.githubusercontent.com" },
    ],
  },

  // Silence noisy Prisma/edge warnings in dev
  serverExternalPackages: ["@prisma/client", "prisma"],
}

export default nextConfig
