import { hasDatabase } from "./db";
import { hasAuthSecret } from "./auth";

// バックエンドの機能が使えるか（データベースと署名の鍵の両方が設定されているとき）
export const backendReady = () => hasDatabase() && hasAuthSecret();

export const json = (data: unknown, status = 200, headers: Record<string, string> = {}) =>
  Response.json(data, { status, headers: { "Cache-Control": "no-store", ...headers } });

export const notReady = () => json({ error: "backend_not_configured" }, 503);

export async function readJson(req: Request): Promise<any> {
  try { return await req.json(); } catch { return null; }
}

// 状態を変える API（POST・PUT・DELETE）の前に呼ぶ。別のサイトからの送信（CSRF）を断る
// - ブラウザが付ける Origin・Sec-Fetch-Site が、このサイト以外を示していたら断る
// - 本文がある API は Content-Type: application/json だけを受け付ける（フォームからの単純な送信を断る）
export function rejectCrossSite(req: Request, { needsJson = true } = {}): Response | null {
  const self = new URL(req.url);
  const origin = req.headers.get("origin");
  if (origin) {
    let o: URL | null = null;
    try { o = new URL(origin); } catch { o = null; }
    const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || self.host;
    if (!o || o.host !== host) return json({ error: "cross_site" }, 403);
  }
  const site = req.headers.get("sec-fetch-site");
  if (site && site !== "same-origin" && site !== "none") return json({ error: "cross_site" }, 403);
  if (needsJson && !(req.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) return json({ error: "unsupported_media_type" }, 415);
  return null;
}

// 回数制限（同じ人・同じ操作が短い時間に何度も来たら断る）。サーバーのインスタンスごとの目安で、
// 何台にも分かれて動く本番では完全ではない。総当たりを遅くするための補助として使う
const buckets = new Map<string, { n: number; reset: number }>();
export function rateLimited(req: Request, name: string, limit: number, windowSec: number, extra = ""): Response | null {
  const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || req.headers.get("x-real-ip") || "local";
  const key = `${name}:${ip}:${extra}`, now = Date.now();
  const b = buckets.get(key);
  if (!b || b.reset < now) { buckets.set(key, { n: 1, reset: now + windowSec * 1000 }); return null; }
  b.n += 1;
  if (buckets.size > 10_000) for (const [k, v] of buckets) if (v.reset < now) buckets.delete(k);
  if (b.n > limit) return json({ error: "rate_limited" }, 429, { "Retry-After": String(Math.ceil((b.reset - now) / 1000)) });
  return null;
}
