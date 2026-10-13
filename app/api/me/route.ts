import { query } from "../../../lib/db";
import { currentUser } from "../../../lib/auth";
import { backendReady, json } from "../../../lib/api";
import { cleanState } from "../../../lib/validate";

export const runtime = "nodejs";

// 画面が最初に呼ぶ。バックエンドが使えるか、ログイン中のユーザーと、保存してある内容を返す
export async function GET() {
  if (!backendReady()) return json({ backend: false });
  const user = await currentUser();
  if (!user) return json({ backend: true, user: null });
  const rows = await query<{ data: Record<string, string> }>("select data from user_state where user_id = $1", [user.id]);
  // 昔の形で保存されたものが残っていても、決まった形のものだけを返す
  return json({ backend: true, user, state: rows[0] ? cleanState(rows[0].data) : null });
}
