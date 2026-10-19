import { cleanAnswers } from "./hearing";
// 画面から送られてくる保存内容（お気に入り・優先順位・重み・置いた家具）を確かめる。
// 決まったキーで、決まった形のものだけを残し、整えた JSON に書き直して保存する（画面側の SYNC_KEY_RE と同じ範囲）
const KEY_RE = /^heyakarte\.(favs|favRanks|weights|hearing|furniture\.[a-z0-9]{1,20})$/;
const PROPERTY_ID_RE = /^[a-z0-9]{1,20}$/;
const FURN_ID_RE = /^f[a-z0-9]{4,24}$/;
const FURN_KINDS = new Set(["bed", "desk", "table", "lowtable", "sofa", "counter", "tub", "washer", "closet", "fridge", "tvstand", "shelf", "chest", "box"]);
const WEIGHT_KEYS = new Set(["shop", "med", "quiet", "commute", "safety", "crime", "food", "conv", "bus"]);

const num = (v: unknown, lo: number, hi: number): v is number => typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;
const parse = (text: string): unknown => { try { return JSON.parse(text); } catch { return undefined; } };

function cleanValue(key: string, text: string): unknown | undefined {
  const v = parse(text);
  if (key === "heyakarte.favs") {
    if (!Array.isArray(v)) return undefined;
    return [...new Set(v.filter((id) => typeof id === "string" && PROPERTY_ID_RE.test(id)))].slice(0, 100);
  }
  if (key === "heyakarte.favRanks") {
    if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
    return Object.fromEntries(Object.entries(v).filter(([id, n]) => PROPERTY_ID_RE.test(id) && Number.isInteger(n) && (n as number) >= 1 && (n as number) <= 100).slice(0, 100));
  }
  if (key === "heyakarte.weights") {
    if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
    return Object.fromEntries(Object.entries(v).filter(([k, n]) => WEIGHT_KEYS.has(k) && [0, 1, 3].includes(n as number)));
  }
  if (key === "heyakarte.hearing") {
    // ヒアリングの結果：終わったか・いつ・選んだ答え・ひとこと・決め方（自由に書いた文は保存しない）
    if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
    const h = v as Record<string, unknown>;
    const answers = cleanAnswers(h.answers) || {};
    return {
      done: h.done === true,
      at: typeof h.at === "string" && /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(h.at) ? h.at : undefined,
      answers,
      summary: typeof h.summary === "string" ? h.summary.slice(0, 200) : "",
      source: h.source === "gemini" ? "gemini" : "rules",
    };
  }
  // heyakarte.furniture.<物件ID>
  if (!Array.isArray(v)) return undefined;
  return v.filter((it: any) => it && typeof it === "object" && typeof it.id === "string" && FURN_ID_RE.test(it.id) && FURN_KINDS.has(it.kind)
      && typeof it.name === "string" && it.name.length <= 60 && num(it.w, 0.05, 4.5) && num(it.d, 0.05, 4.5)
      && (it.h === undefined || it.h === null || num(it.h, 0.05, 3)) && num(it.x, -5, 30) && num(it.z, -5, 30)
      && Number.isInteger(it.rot ?? 0) && (it.rot ?? 0) >= 0 && (it.rot ?? 0) <= 3)
    .slice(0, 60)
    .map((it: any) => ({ id: it.id, kind: it.kind, name: it.name, w: it.w, d: it.d, ...(num(it.h, 0.05, 3) ? { h: it.h } : {}), x: it.x, z: it.z, rot: it.rot ?? 0 }));
}

// 返り値：保存してよい内容（キー → JSON 文字列）。家具は物件50件まで
export function cleanState(data: unknown): Record<string, string> | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const out: Record<string, string> = {};
  let furnitureKeys = 0;
  for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
    if (!KEY_RE.test(k) || typeof v !== "string" || v.length > 50_000) continue;
    if (k.startsWith("heyakarte.furniture.") && ++furnitureKeys > 50) continue;
    const clean = cleanValue(k, v);
    if (clean !== undefined) out[k] = JSON.stringify(clean);
  }
  return out;
}
