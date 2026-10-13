import { query } from "../../../../lib/db";
import { hashPassword, startSession, USERNAME_RE, validPassword } from "../../../../lib/auth";
import { backendReady, json, notReady, rateLimited, readJson, rejectCrossSite } from "../../../../lib/api";

export const runtime = "nodejs";

export async function POST(req: Request) {
  if (!backendReady()) return notReady();
  const blocked = rejectCrossSite(req) || rateLimited(req, "register", 5, 60 * 60);
  if (blocked) return blocked;
  const body = await readJson(req);
  const username = typeof body?.username === "string" ? body.username.trim() : "";
  if (!USERNAME_RE.test(username)) return json({ error: "bad_username" }, 400);
  if (!validPassword(body?.password)) return json({ error: "bad_password" }, 400);
  const hash = await hashPassword(body.password);
  // role は常に 'user'（管理者は scripts/create-admin.mjs でだけ作る）
  const rows = await query<{ id: number; username: string; role: string; token_version: number }>(
    "insert into users (username, password_hash, role) values ($1, $2, 'user') on conflict (username) do nothing returning id, username, role, token_version",
    [username, hash],
  );
  if (!rows[0]) return json({ error: "username_taken" }, 409);
  await startSession(rows[0].id, rows[0].token_version);
  return json({ user: { id: rows[0].id, username: rows[0].username, role: rows[0].role } });
}
