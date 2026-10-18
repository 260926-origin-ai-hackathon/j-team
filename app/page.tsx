import { headers } from "next/headers";
import Script from "next/script";
// 画面の HTML は index.html から取り出したもの（scripts/build-next.mjs が作る）
import markup from "./_generated/markup";

// CSP の nonce をリクエストごとに付けるため、毎回サーバーで描く（proxy.ts を参照）
export default async function Page() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <>
      <div className="markup-root" dangerouslySetInnerHTML={{ __html: markup }} />
      {/* 3D（window.Room3D）とアプリ本体。アプリ本体は 3D を部屋のタブを開いたときにだけ使うので、読み込む順番には依存しない。
          lazyOnload だと、タブが裏にあるときなどに読み込みが止まることがあるので、どちらもすぐに読み込む */}
      <Script src="/heyakarte/room3d.js" strategy="afterInteractive" nonce={nonce} />
      <Script src="/heyakarte/app.js" strategy="afterInteractive" nonce={nonce} />
    </>
  );
}
