import { readFileSync } from "node:fs";
import path from "node:path";
import Script from "next/script";

// 画面の HTML は index.html から取り出したもの（ビルドのときに読み込み、静的なページにする）
const markup = readFileSync(path.join(process.cwd(), "app/_generated/markup.html"), "utf8");

export default function Page() {
  return (
    <>
      <div style={{ display: "contents" }} dangerouslySetInnerHTML={{ __html: markup }} />
      {/* 3D（window.Room3D）を先に、アプリ本体をあとに読み込む */}
      <Script src="/heyakarte/room3d.js" strategy="afterInteractive" />
      <Script src="/heyakarte/app.js" strategy="lazyOnload" />
    </>
  );
}
