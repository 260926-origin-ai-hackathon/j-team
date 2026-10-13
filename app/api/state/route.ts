import { query } from "../../../lib/db";
import { currentUser } from "../../../lib/auth";
import { backendReady, json, notReady, rateLimited, readJson, rejectCrossSite } from "../../../lib/api";
import { cleanState } from "../../../lib/validate";

export const runtime = "nodejs";

// ログイン中のユーザーの保存内容（お気に入り・優先順位・重み・置いた家具など）を丸ごと置き換える
// 中身は画面が localStorage に入れている決まった項目（キー → JSON 文字列）。lib/validate.ts で形を確かめ、合わないものは捨てる
const MAX_BYTES = 200_000;

export async function PUT(req: Request) {
  if (!backendReady()) return notReady();
  const blocked = rejectCrossSite(req) || rateLimited(req, "state", 120, 600);
  if (blocked) return blocked;
  const user = await currentUser();
  if (!user) return json({ error: "not_logged_in" }, 401);
  const body = await readJson(req);
  const clean = cleanState(body?.data);
  if (!clean) return json({ error: "bad_request" }, 400);
  const text = JSON.stringify(clean);
  if (text.length > MAX_BYTES) return json({ error: "too_large" }, 413);
  await query(
    `insert into user_state (user_id, data, updated_at) values ($1, $2, now())
     on conflict (user_id) do update set data = excluded.data, updated_at = now()`,
    [user.id, text],
  );
  return json({ ok: true });
}
