import { NextRequest, NextResponse } from "next/server";

// ページ（HTML）に Content Security Policy を付ける。スクリプトはリクエストごとの nonce が付いたものと、
// それが読み込んだもの（'strict-dynamic'）だけを動かす。外部への通信・埋め込み・フォーム送信先も絞る
// - style 属性（style="…"）は許さない。画面の色や幅は data- 属性から JavaScript（CSSOM）で入れる（index.html の applyDataStyles）
// - 地図のヒートマップは canvas から作った data: の画像
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const dev = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}' https://fonts.googleapis.com`,
    "img-src 'self' data: blob:",
    "font-src 'self' https://fonts.gstatic.com",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(dev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // API・静的ファイル・データには付けない（HTML のページだけ）
      source: "/((?!api|_next/static|_next/image|heyakarte/|vendor/|data/|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
