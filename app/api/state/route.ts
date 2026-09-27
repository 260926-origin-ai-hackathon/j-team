import { query } from "../../../lib/db";
import { currentUser } from "../../../lib/auth";
import { backendReady, json, notReady, readJson } from "../../../lib/api";

export const runtime = "nodejs";

// ログイン中のユーザーの保存内容（お気に入り・優先順位・重み・置いた家具など）を丸ごと置き換える
// 中身は画面が localStorage に入れている「heyakarte.」で始まる項目（キー → 文字列）
const MAX_BYTES = 200_000;

export async function PUT(req: Request) {
  if (!backendReady()) return notReady();
  const user = await currentUser();
  if (!user) return json({ error: "not_logged_in" }, 401);
  const body = await readJson(req);
  const data = body?.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return json({ error: "bad_request" }, 400);
  const clean: Record<string, string> = {};
  for (const [k, v] of Object.entries(data)) {
    if (k.startsWith("heyakarte.") && k.length <= 100 && typeof v === "string") clean[k] = v;
  }
  const text = JSON.stringify(clean);
  if (text.length > MAX_BYTES) return json({ error: "too_large" }, 413);
  await query(
    `insert into user_state (user_id, data, updated_at) values ($1, $2, now())
     on conflict (user_id) do update set data = excluded.data, updated_at = now()`,
    [user.id, text],
  );
  return json({ ok: true });
}
