import { query } from "../../../../lib/db";
import { burnPasswordCheck, startSession, verifyPassword } from "../../../../lib/auth";
import { backendReady, json, notReady, rateLimited, readJson, rejectCrossSite } from "../../../../lib/api";

export const runtime = "nodejs";

export async function POST(req: Request) {
  if (!backendReady()) return notReady();
  const crossSite = rejectCrossSite(req);
  if (crossSite) return crossSite;
  const body = await readJson(req);
  const username = typeof body?.username === "string" ? body.username.trim().slice(0, 24) : "";
  const password = typeof body?.password === "string" ? body.password.slice(0, 128) : "";
  // 同じ接続元から10分に20回、同じユーザー名へは10分に8回まで
  const limited = rateLimited(req, "login", 20, 600) || rateLimited(req, "login-user", 8, 600, username.toLowerCase());
  if (limited) return limited;
  const rows = await query<{ id: number; username: string; role: string; password_hash: string; token_version: number }>(
    "select id, username, role, password_hash, token_version from users where username = $1", [username],
  );
  const u = rows[0];
  const ok = u ? await verifyPassword(password, u.password_hash) : await burnPasswordCheck(password);
  if (!u || !password || !ok) {
    await new Promise((r) => setTimeout(r, 400)); // 総当たりを少しでも遅くする
    return json({ error: "wrong_credentials" }, 401);
  }
  await startSession(u.id, u.token_version);
  return json({ user: { id: u.id, username: u.username, role: u.role } });
}
