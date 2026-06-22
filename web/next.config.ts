import type { NextConfig } from 'next'

const API_PROXY_TARGET =
  process.env.API_PROXY_TARGET ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${API_PROXY_TARGET}/api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
