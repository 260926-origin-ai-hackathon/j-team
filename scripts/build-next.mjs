// index.html（アプリ本体。Claude Artifact 版もこのファイル）を、Next.js で配る形に分ける。
// `npm run dev` / `npm run build` の前に自動で動く。作ったファイルは git に入れない。
//   CSS         → public/heyakarte/app.css
//   画面の HTML → app/_generated/markup.html（app/page.tsx が読み込む）
//   JavaScript  → public/heyakarte/room3d.js（3D）・app.js（アプリ本体）
//   周辺データ  → public/data/area.json
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";

const html = readFileSync("index.html", "utf8");

const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map((m) => m[1]);
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (styles.length === 0 || scripts.length !== 2) {
  throw new Error(`index.html の形が想定と違います（style ${styles.length}個・script ${scripts.length}個）`);
}
const bodyStart = html.lastIndexOf("</style>") + "</style>".length;
const markup = html.slice(bodyStart, html.indexOf("<script>", bodyStart)).trim();

mkdirSync("app/_generated", { recursive: true });
mkdirSync("public/heyakarte", { recursive: true });
mkdirSync("public/data", { recursive: true });
writeFileSync("public/heyakarte/app.css", styles.join("\n"));
writeFileSync("app/_generated/markup.html", markup);
writeFileSync("public/heyakarte/room3d.js", scripts[0]);
writeFileSync("public/heyakarte/app.js", scripts[1]);
copyFileSync("data/area.json", "public/data/area.json");

console.log(`index.html を分けました（CSS ${styles.length}個・script 2個・画面 ${markup.length}文字）`);
