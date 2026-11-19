/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === "development";

const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: false,
  reactStrictMode: true,
  // Dev server only: proxy API + SSE to the FastAPI backend. Rewrites are not
  // supported (or needed) in the static export, which is served same-origin.
  ...(isDev
    ? {
        async rewrites() {
          return [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }];
        },
      }
    : {}),
};

export default nextConfig;
