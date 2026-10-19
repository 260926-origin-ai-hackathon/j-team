import { currentUser } from "../../../lib/auth";
import { analyzeHearing, hasGemini } from "../../../lib/gemini";
import { cleanAnswers, cleanWeights } from "../../../lib/hearing";
import { backendReady, json, notReady, rateLimited, readJson, rejectCrossSite } from "../../../lib/api";

export const runtime = "nodejs";

// 画面が最初に聞く：Gemini で重みを決められるか
export async function GET() {
  return json({ ai: backendReady() && hasGemini() });
}

// ヒアリングの答えから、Gemini で重みとひとことを決める（ログインした人だけ）。
// 答えと自由に書いた文は Gemini に送るだけで、このサーバーには保存しない
export async function POST(req: Request) {
  if (!backendReady()) return notReady();
  if (!hasGemini()) return json({ error: "ai_not_configured" }, 503);
  const blocked = rejectCrossSite(req) || rateLimited(req, "hearing", 10, 600);
  if (blocked) return blocked;
  const user = await currentUser();
  if (!user) return json({ error: "not_logged_in" }, 401);
  const body = await readJson(req);
  const answers = cleanAnswers(body?.answers);
  const baseline = cleanWeights(body?.baseline);
  const note = typeof body?.note === "string" ? body.note.replace(/\s+/g, " ").trim().slice(0, 300) : "";
  if (!answers || !baseline) return json({ error: "bad_request" }, 400);
  try {
    const out = await analyzeHearing(answers, note, baseline);
    if (!out) return json({ error: "ai_failed" }, 502);
    return json({ ...out, source: "gemini" });
  } catch {
    return json({ error: "ai_failed" }, 502);
  }
}
