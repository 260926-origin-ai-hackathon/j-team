import { createHmac, randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { cookies } from "next/headers";
import { query } from "./db";

// ログインのしくみ
// - パスワードは scrypt でハッシュ化して保存する（元のパスワードは保存しない）
// - ログイン状態は「ユーザーID・トークンの世代・期限・署名」の入った Cookie で持つ。署名の鍵は環境変数 AUTH_SECRET
// - ログアウトするとユーザーの「トークンの世代」を1つ進め、それまでに発行したすべての Cookie（ほかの端末も）を無効にする
const scrypt = promisify(scryptCb) as (pw: string, salt: Buffer, len: number) => Promise<Buffer>;
const SECURE = process.env.NODE_ENV === "production";
// 本番は __Host- を付ける（HTTPS・このサイトだけ・パス / に限られ、サブドメインから上書きできない）
const COOKIE = SECURE ? "__Host-heyakarte_session" : "heyakarte_session";
const MAX_AGE = 60 * 60 * 24 * 14; // 14日

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

// ユーザーがいないときも同じくらい時間をかけて、ユーザー名があるかどうかを応答時間から分からないようにする
const DUMMY_HASH = "scrypt$AAAAAAAAAAAAAAAAAAAAAA==$" + Buffer.alloc(64).toString("base64");
export const burnPasswordCheck = (password: string) => verifyPassword(password, DUMMY_HASH).catch(() => false);

const sign = (payload: string) => createHmac("sha256", process.env.AUTH_SECRET!).update(payload).digest("base64url");

export async function startSession(userId: number, tokenVersion: number) {
  const payload = Buffer.from(JSON.stringify({ uid: userId, ver: tokenVersion, exp: Math.floor(Date.now() / 1000) + MAX_AGE })).toString("base64url");
  (await cookies()).set(COOKIE, `${payload}.${sign(payload)}`, {
    httpOnly: true, secure: SECURE, sameSite: "lax", path: "/", maxAge: MAX_AGE,
  });
}

export async function endSession(user: User | null) {
  if (user) await query("update users set token_version = token_version + 1 where id = $1", [user.id]);
  (await cookies()).delete(COOKIE);
}

// Cookie からいまのユーザーを取り出す。署名が合わない・期限切れ・世代が古い・削除済みのユーザーなら null
export async function currentUser(): Promise<User | null> {
  if (!hasAuthSecret()) return null;
  const raw = (await cookies()).get(COOKIE)?.value;
  if (!raw) return null;
  const [payload, sig] = raw.split(".");
  if (!payload || !sig) return null;
  const good = Buffer.from(sign(payload)), got = Buffer.from(sig);
  if (good.length !== got.length || !timingSafeEqual(good, got)) return null;
  let data: { uid?: number; ver?: number; exp?: number };
  try { data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")); } catch { return null; }
  if (!Number.isInteger(data.uid) || !Number.isInteger(data.ver) || !data.exp || data.exp < Date.now() / 1000) return null;
  const rows = await query<User & { token_version: number }>("select id, username, role, token_version from users where id = $1", [data.uid]);
  const u = rows[0];
  if (!u || u.token_version !== data.ver) return null;
  return { id: u.id, username: u.username, role: u.role };
}

// ユーザー名は半角英数字と _ - の3〜24文字、パスワードは8〜128文字
export const USERNAME_RE = /^[A-Za-z0-9_-]{3,24}$/;
export const validPassword = (pw: unknown): pw is string => typeof pw === "string" && pw.length >= 8 && pw.length <= 128;
