// 管理者（物件の掲載情報を変えられる人）を作る・既存のユーザーを管理者にする
//   DATABASE_URL=... node scripts/create-admin.mjs <ユーザー名>
// パスワードは画面に表示せずに入力する（すでにいるユーザーを管理者にするだけなら、何も入れずに Enter）
import { randomBytes, scrypt as scryptCb } from "node:crypto";
import { promisify } from "node:util";
import pg from "pg";

const scrypt = promisify(scryptCb);
const username = process.argv[2];
if (!process.env.DATABASE_URL) { console.error("DATABASE_URL を設定してください"); process.exit(1); }
if (!/^[A-Za-z0-9_-]{3,24}$/.test(username || "")) { console.error("使い方: node scripts/create-admin.mjs <ユーザー名（半角英数字と _ - の3〜24文字）>"); process.exit(1); }

function askHidden(label) {
  return new Promise((resolve) => {
    process.stdout.write(label);
    const stdin = process.stdin;
    if (!stdin.isTTY) { let buf = ""; stdin.on("data", (d) => (buf += d)); stdin.on("end", () => resolve(buf.trim())); return; }
    stdin.setRawMode(true); stdin.resume(); stdin.setEncoding("utf8");
    let pw = "";
    const onData = (ch) => {
      if (ch === "\r" || ch === "\n") { stdin.setRawMode(false); stdin.pause(); stdin.off("data", onData); process.stdout.write("\n"); resolve(pw); }
      else if (ch === "\u0003") process.exit(1);
      else if (ch === "\u007f") pw = pw.slice(0, -1);
      else pw += ch;
    };
    stdin.on("data", onData);
  });
}

const password = await askHidden("パスワード（8文字以上。既存ユーザーを管理者にするだけなら空のまま Enter）: ");
if (password && password.length < 8) { console.error("パスワードは8文字以上にしてください"); process.exit(1); }

const local = /@(localhost|127\.0\.0\.1)[:/]/.test(process.env.DATABASE_URL);
const client = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: local ? undefined : { rejectUnauthorized: false } });
await client.connect();
await client.query(`create table if not exists users (
  id serial primary key, username text not null unique, password_hash text not null,
  role text not null default 'user', created_at timestamptz not null default now())`);
if (password) {
  const salt = randomBytes(16);
  const hash = `scrypt$${salt.toString("base64")}$${(await scrypt(password, salt, 64)).toString("base64")}`;
  await client.query(
    `insert into users (username, password_hash, role) values ($1, $2, 'admin')
     on conflict (username) do update set password_hash = excluded.password_hash, role = 'admin'`, [username, hash]);
} else {
  const r = await client.query("update users set role = 'admin' where username = $1", [username]);
  if (!r.rowCount) { console.error(`ユーザー ${username} がいません。パスワードを入れて作り直してください`); process.exit(1); }
}
await client.end();
console.log(`${username} を管理者にしました`);
