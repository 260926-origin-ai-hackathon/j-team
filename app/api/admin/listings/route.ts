import { query } from "../../../../lib/db";
import { currentUser } from "../../../../lib/auth";
import { backendReady, json, notReady, readJson } from "../../../../lib/api";

export const runtime = "nodejs";

// 管理者だけが物件の掲載情報を変える。空欄（null）の項目は data/area.json の値のまま
async function requireAdmin() {
  if (!backendReady()) return { error: notReady() };
  const user = await currentUser();
  if (!user) return { error: json({ error: "not_logged_in" }, 401) };
  if (user.role !== "admin") return { error: json({ error: "forbidden" }, 403) };
  return { user };
}

const intOrNull = (v: unknown, max: number) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 && n <= max ? n : undefined;
};
const monthsOrNull = (v: unknown) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= 12 && Math.round(n * 2) === n * 2 ? n : undefined; // 0.5か月刻み
};

export async function PUT(req: Request) {
  const { user, error } = await requireAdmin();
  if (error) return error;
  const b = await readJson(req);
  const id = typeof b?.propertyId === "string" ? b.propertyId : "";
  if (!/^[a-z0-9]{1,20}$/.test(id)) return json({ error: "bad_property" }, 400);
  const name = b.name === null || b.name === undefined || b.name === "" ? null : String(b.name).trim().slice(0, 60);
  const rent = intOrNull(b.rent, 1_000_000), fee = intOrNull(b.fee, 200_000);
  const deposit = monthsOrNull(b.deposit), key = monthsOrNull(b.key);
  if ([rent, fee, deposit, key].includes(undefined)) return json({ error: "bad_value" }, 400);
  const published = b.published !== false;
  await query(
    `insert into listings (property_id, name, rent, fee, deposit, key_money, published, updated_at, updated_by)
     values ($1, $2, $3, $4, $5, $6, $7, now(), $8)
     on conflict (property_id) do update set name = excluded.name, rent = excluded.rent, fee = excluded.fee,
       deposit = excluded.deposit, key_money = excluded.key_money, published = excluded.published,
       updated_at = now(), updated_by = excluded.updated_by`,
    [id, name, rent, fee, deposit, key, published, user!.id],
  );
  return json({ ok: true });
}

// 掲載情報を消して、data/area.json の値に戻す
export async function DELETE(req: Request) {
  const { error } = await requireAdmin();
  if (error) return error;
  const id = new URL(req.url).searchParams.get("propertyId") || "";
  if (!/^[a-z0-9]{1,20}$/.test(id)) return json({ error: "bad_property" }, 400);
  await query("delete from listings where property_id = $1", [id]);
  return json({ ok: true });
}
