import { endSession } from "../../../../lib/auth";
import { json } from "../../../../lib/api";

export const runtime = "nodejs";

export async function POST() {
  await endSession();
  return json({ ok: true });
}
