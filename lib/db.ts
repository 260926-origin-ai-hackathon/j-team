import { Pool } from "pg";

// Postgres への接続。DATABASE_URL が無いときはバックエンドの機能（ログイン・同期・物件の管理）を使わない
// 本番は Vercel から作れる Neon などの Postgres、手元は Docker の Postgres を想定している
export const hasDatabase = () => Boolean(process.env.DATABASE_URL);

const globalForPool = globalThis as unknown as { heyakartePool?: Pool; heyakarteSchema?: Promise<void> };

function pool(): Pool {
  if (!globalForPool.heyakartePool) {
    const url = process.env.DATABASE_URL!;
    const local = /@(localhost|127\.0\.0\.1)[:/]/.test(url);
    globalForPool.heyakartePool = new Pool({ connectionString: url, max: 5, ssl: local ? undefined : { rejectUnauthorized: false } });
  }
  return globalForPool.heyakartePool;
}

// 表が無ければ作る（最初の1回だけ）
const SCHEMA = `
  create table if not exists users (
    id serial primary key,
    username text not null unique,
    password_hash text not null,
    role text not null default 'user',
    created_at timestamptz not null default now()
  );
  create table if not exists user_state (
    user_id integer primary key references users(id) on delete cascade,
    data jsonb not null default '{}',
    updated_at timestamptz not null default now()
  );
  create table if not exists listings (
    property_id text primary key,
    name text,
    rent integer,
    fee integer,
    deposit numeric,
    key_money numeric,
    published boolean not null default true,
    updated_at timestamptz not null default now(),
    updated_by integer references users(id) on delete set null
  );
`;

export async function query<T = any>(text: string, params: unknown[] = []): Promise<T[]> {
  if (!globalForPool.heyakarteSchema) globalForPool.heyakarteSchema = pool().query(SCHEMA).then(() => undefined);
  try {
    await globalForPool.heyakarteSchema;
  } catch (e) {
    globalForPool.heyakarteSchema = undefined; // 次のリクエストで作り直しを試す
    throw e;
  }
  const r = await pool().query(text, params);
  return r.rows as T[];
}
