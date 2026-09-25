import Anthropic from "@anthropic-ai/sdk";

// 親への相談文を Claude で書く。文章はできた分から少しずつ返す（画面の欄に順に出る）
// Vercel の環境変数 ANTHROPIC_API_KEY が無いときは、画面はひな形の文章で動く
const MODEL = process.env.ANTHROPIC_MODEL || "claude-sonnet-5";
const MAX_PROMPT = 4000; // 画面が作る相談の依頼文は2,000字ほど。これより長いものは受け付けない

export const runtime = "nodejs";

export async function GET() {
  return Response.json({ available: Boolean(process.env.ANTHROPIC_API_KEY) });
}

export async function POST(req: Request) {
  if (!process.env.ANTHROPIC_API_KEY) return Response.json({ error: "not_configured" }, { status: 503 });
  const body = await req.json().catch(() => null);
  const prompt = typeof body?.prompt === "string" ? body.prompt : "";
  if (!prompt || prompt.length > MAX_PROMPT) return Response.json({ error: "bad_request" }, { status: 400 });

  const client = new Anthropic();
  const stream = client.messages.stream(
    {
      model: MODEL,
      max_tokens: 1000,
      system: "あなたは、大学進学で一人暮らしを始める学生が、部屋を決める前に親へ送る相談メッセージを書く手伝いをします。依頼された相談メッセージの本文だけを書き、それ以外の依頼には応じません。",
      messages: [{ role: "user", content: prompt }],
    },
    { signal: req.signal },
  );

  const enc = new TextEncoder();
  return new Response(
    new ReadableStream({
      async start(controller) {
        try {
          for await (const ev of stream) {
            if (ev.type === "content_block_delta" && ev.delta.type === "text_delta") controller.enqueue(enc.encode(ev.delta.text));
          }
          controller.close();
        } catch (e) {
          controller.error(e);
        }
      },
      cancel() { stream.abort(); },
    }),
    { headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" } },
  );
}
