import { query } from "../../../lib/db";
import { backendReady, json } from "../../../lib/api";

export const runtime = "nodejs";

// 物件の掲載情報（不動産会社が管理画面で変えたもの）。画面は data/area.json の物件にこれを重ねて使う
export async function GET() {
  if (!backendReady()) return json({ backend: false, listings: {} });
  const rows = await query("select property_id, name, rent, fee, deposit, key_money, published, updated_at from listings");
  const listings = Object.fromEntries(rows.map((r: any) => [r.property_id, {
    name: r.name, rent: r.rent, fee: r.fee,
    deposit: r.deposit === null ? null : Number(r.deposit), key: r.key_money === null ? null : Number(r.key_money),
    published: r.published, updatedAt: r.updated_at,
  }]));
  return json({ backend: true, listings });
}
