import { query } from "../../../../lib/db";
import { startSession, verifyPassword } from "../../../../lib/auth";
import { backendReady, json, notReady, readJson } from "../../../../lib/api";

export const runtime = "nodejs";

export async function POST(req: Request) {
  if (!backendReady()) return notReady();
  const body = await readJson(req);
  const username = typeof body?.username === "string" ? body.username.trim() : "";
  const password = typeof body?.password === "string" ? body.password : "";
  const rows = await query<{ id: number; username: string; role: string; password_hash: string }>(
    "select id, username, role, password_hash from users where username = $1", [username],
  );
  const u = rows[0];
  if (!u || !password || !(await verifyPassword(password, u.password_hash))) {
    await new Promise((r) => setTimeout(r, 400)); // 総当たりを少しでも遅くする
    return json({ error: "wrong_credentials" }, 401);
  }
  await startSession(u.id);
  return json({ user: { id: u.id, username: u.username, role: u.role } });
}
