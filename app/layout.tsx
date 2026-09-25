import type { Metadata, Viewport } from "next";
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
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
        <Script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js" strategy="beforeInteractive" />
        {/* Next.js 版では、親への相談文の AI をサーバーの /api/letter で動かす */}
        <Script id="heyakarte-server-ai" strategy="beforeInteractive">{`window.__HEYAKARTE_SERVER_AI__ = true;`}</Script>
      </body>
    </html>
  );
}
