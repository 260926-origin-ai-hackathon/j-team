import { query } from "../../../../lib/db";
import { currentUser, endSession, verifyPassword } from "../../../../lib/auth";
import { backendReady, json, notReady, rateLimited, readJson, rejectCrossSite } from "../../../../lib/api";

export const runtime = "nodejs";

// アカウントを消す。パスワードを確かめてから、ユーザーと保存内容（お気に入りなど）を消す
export async function POST(req: Request) {
  if (!backendReady()) return notReady();
  const blocked = rejectCrossSite(req) || rateLimited(req, "delete", 5, 600);
  if (blocked) return blocked;
  const user = await currentUser();
  if (!user) return json({ error: "not_logged_in" }, 401);
  if (user.role === "admin") return json({ error: "admin_cannot_delete" }, 403); // 管理者は画面から消さない
  const body = await readJson(req);
  const password = typeof body?.password === "string" ? body.password.slice(0, 128) : "";
  const rows = await query<{ password_hash: string }>("select password_hash from users where id = $1", [user.id]);
  if (!rows[0] || !(await verifyPassword(password, rows[0].password_hash))) {
    await new Promise((r) => setTimeout(r, 400));
    return json({ error: "wrong_password" }, 401);
  }
  await query("delete from users where id = $1", [user.id]); // user_state は on delete cascade で一緒に消える
  await endSession(null);
  return json({ ok: true });
}
