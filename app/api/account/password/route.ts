import { query } from "../../../../lib/db";
import { currentUser, hashPassword, startSession, validPassword, verifyPassword } from "../../../../lib/auth";
import { backendReady, json, notReady, rateLimited, readJson, rejectCrossSite } from "../../../../lib/api";

export const runtime = "nodejs";

// パスワードを変える。いまのパスワードを確かめ、変えたらほかの端末のログインも無効にする（この端末はログインしたまま）
export async function POST(req: Request) {
  if (!backendReady()) return notReady();
  const blocked = rejectCrossSite(req) || rateLimited(req, "password", 8, 600);
  if (blocked) return blocked;
  const user = await currentUser();
  if (!user) return json({ error: "not_logged_in" }, 401);
  const body = await readJson(req);
  const current = typeof body?.current === "string" ? body.current.slice(0, 128) : "";
  if (!validPassword(body?.next)) return json({ error: "bad_password" }, 400);
  const rows = await query<{ password_hash: string }>("select password_hash from users where id = $1", [user.id]);
  if (!rows[0] || !(await verifyPassword(current, rows[0].password_hash))) {
    await new Promise((r) => setTimeout(r, 400));
    return json({ error: "wrong_password" }, 401);
  }
  const updated = await query<{ token_version: number }>(
    "update users set password_hash = $1, token_version = token_version + 1 where id = $2 returning token_version",
    [await hashPassword(body.next), user.id],
  );
  await startSession(user.id, updated[0].token_version);
  return json({ ok: true });
}
