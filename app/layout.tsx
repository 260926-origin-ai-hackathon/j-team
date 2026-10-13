import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import Script from "next/script";

export const metadata: Metadata = {
  title: "ヘヤカルテ",
  description: "内見に行く前に、部屋の「まわり」まで分かる部屋探しアプリ",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // proxy.ts がリクエストごとに作る nonce。これが付いたスクリプトだけが動く（CSP）
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="ja">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&family=Zen+Kaku+Gothic+New:wght@700;900&display=swap"
        />
        {/* 画面の見た目は index.html の CSS をそのまま使う（scripts/build-next.mjs が書き出す） */}
        <link rel="stylesheet" href="/heyakarte/app.css" />
      </head>
      <body>
        {children}
        {/* Leaflet と three.js は npm の固定版をこのサイトから配る（外部の配信元が改ざんされても影響を受けない） */}
        <Script src="/vendor/leaflet/leaflet.js" strategy="beforeInteractive" nonce={nonce} />
        {/* Next.js 版では、親への相談文の AI（/api/letter）と、ログイン・物件の掲載情報（/api/me・/api/listings）をサーバーで動かす */}
        <Script id="heyakarte-server" strategy="beforeInteractive" nonce={nonce}>{`window.__HEYAKARTE_SERVER_AI__ = true; window.__HEYAKARTE_SERVER__ = true; window.__HEYAKARTE_THREE_URL__ = "/vendor/three/three.module.min.js";`}</Script>
      </body>
    </html>
  );
}
