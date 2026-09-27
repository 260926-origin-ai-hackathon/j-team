import { hasDatabase } from "./db";
import { hasAuthSecret } from "./auth";

// バックエンドの機能が使えるか（データベースと署名の鍵の両方が設定されているとき）
export const backendReady = () => hasDatabase() && hasAuthSecret();

export const json = (data: unknown, status = 200) =>
  Response.json(data, { status, headers: { "Cache-Control": "no-store" } });

export const notReady = () => json({ error: "backend_not_configured" }, 503);

export async function readJson(req: Request): Promise<any> {
  try { return await req.json(); } catch { return null; }
}
