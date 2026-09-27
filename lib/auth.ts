import { createHmac, randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { cookies } from "next/headers";
import { query } from "./db";

// ログインのしくみ
// - パスワードは scrypt でハッシュ化して保存する（元のパスワードは保存しない）
// - ログイン状態は「ユーザーID・期限・署名」の入った Cookie で持つ。署名の鍵は環境変数 AUTH_SECRET
const scrypt = promisify(scryptCb) as (pw: string, salt: Buffer, len: number) => Promise<Buffer>;
const COOKIE = "heyakarte_session";
const MAX_AGE = 60 * 60 * 24 * 30; // 30日

export type User = { id: number; username: string; role: string };

export const hasAuthSecret = () => (process.env.AUTH_SECRET || "").length >= 32;

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const hash = await scrypt(password, salt, 64);
  return `scrypt$${salt.toString("base64")}$${hash.toString("base64")}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const [kind, saltB64, hashB64] = stored.split("$");
  if (kind !== "scrypt" || !saltB64 || !hashB64) return false;
  const expected = Buffer.from(hashB64, "base64");
  const actual = await scrypt(password, Buffer.from(saltB64, "base64"), expected.length);
  return timingSafeEqual(actual, expected);
}

const sign = (payload: string) => createHmac("sha256", process.env.AUTH_SECRET!).update(payload).digest("base64url");

export async function startSession(userId: number) {
  const payload = Buffer.from(JSON.stringify({ uid: userId, exp: Math.floor(Date.now() / 1000) + MAX_AGE })).toString("base64url");
  (await cookies()).set(COOKIE, `${payload}.${sign(payload)}`, {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: MAX_AGE,
  });
}

export async function endSession() {
  (await cookies()).delete(COOKIE);
}

// Cookie からいまのユーザーを取り出す。署名が合わない・期限切れ・削除済みのユーザーなら null
export async function currentUser(): Promise<User | null> {
  if (!hasAuthSecret()) return null;
  const raw = (await cookies()).get(COOKIE)?.value;
  if (!raw) return null;
  const [payload, sig] = raw.split(".");
  if (!payload || !sig) return null;
  const good = Buffer.from(sign(payload)), got = Buffer.from(sig);
  if (good.length !== got.length || !timingSafeEqual(good, got)) return null;
  let data: { uid?: number; exp?: number };
  try { data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")); } catch { return null; }
  if (!data.uid || !data.exp || data.exp < Date.now() / 1000) return null;
  const rows = await query<User>("select id, username, role from users where id = $1", [data.uid]);
  return rows[0] || null;
}

// ユーザー名は半角英数字と _ - の3〜24文字、パスワードは8〜128文字
export const USERNAME_RE = /^[A-Za-z0-9_-]{3,24}$/;
export const validPassword = (pw: unknown): pw is string => typeof pw === "string" && pw.length >= 8 && pw.length <= 128;
