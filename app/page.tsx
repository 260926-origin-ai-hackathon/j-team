import { headers } from "next/headers";
import Script from "next/script";
// 画面の HTML は index.html から取り出したもの（scripts/build-next.mjs が作る）
import markup from "./_generated/markup";

// CSP の nonce をリクエストごとに付けるため、毎回サーバーで描く（proxy.ts を参照）
export default async function Page() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <>
      <div style={{ display: "contents" }} dangerouslySetInnerHTML={{ __html: markup }} />
      {/* 3D（window.Room3D）を先に、アプリ本体をあとに読み込む */}
      <Script src="/heyakarte/room3d.js" strategy="afterInteractive" nonce={nonce} />
      <Script src="/heyakarte/app.js" strategy="lazyOnload" nonce={nonce} />
    </>
  );
}
