import { currentUser, endSession } from "../../../../lib/auth";
import { backendReady, json, rejectCrossSite } from "../../../../lib/api";

export const runtime = "nodejs";

// ログアウト：Cookie を消し、そのユーザーがほかの端末で持っているログイン状態もまとめて無効にする
export async function POST(req: Request) {
  const crossSite = rejectCrossSite(req, { needsJson: false });
  if (crossSite) return crossSite;
  const user = backendReady() ? await currentUser() : null;
  await endSession(user);
  return json({ ok: true });
}
