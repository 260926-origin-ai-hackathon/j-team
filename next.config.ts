import type { NextConfig } from "next";

// すべての応答に付けるセキュリティヘッダー（CSP は proxy.ts でページごとに付ける）
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" }, // 他のサイトに埋め込ませない（古いブラウザ向け。新しいブラウザは CSP の frame-ancestors）
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
