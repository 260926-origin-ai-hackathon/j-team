import { query } from "../../../../lib/db";
import { hashPassword, startSession, USERNAME_RE, validPassword } from "../../../../lib/auth";
import { backendReady, json, notReady, readJson } from "../../../../lib/api";

export const runtime = "nodejs";

export async function POST(req: Request) {
  if (!backendReady()) return notReady();
  const body = await readJson(req);
  const username = typeof body?.username === "string" ? body.username.trim() : "";
  if (!USERNAME_RE.test(username)) return json({ error: "bad_username" }, 400);
  if (!validPassword(body?.password)) return json({ error: "bad_password" }, 400);
  const hash = await hashPassword(body.password);
  const rows = await query<{ id: number; username: string; role: string }>(
    "insert into users (username, password_hash) values ($1, $2) on conflict (username) do nothing returning id, username, role",
    [username, hash],
  );
  if (!rows[0]) return json({ error: "username_taken" }, 409);
  await startSession(rows[0].id);
  return json({ user: rows[0] });
}
