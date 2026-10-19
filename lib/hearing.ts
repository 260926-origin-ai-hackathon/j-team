// ヘヤまるのヒアリング（ログインしたあとに聞く質問）。画面（index.html の HEARING）と同じ id・選択肢にそろえる
export const WEIGHT_KEYS = ["shop", "med", "quiet", "commute", "safety", "crime", "food", "conv", "bus"] as const;
export type WeightKey = (typeof WEIGHT_KEYS)[number];
export type Weights = Record<WeightKey, 0 | 1 | 3>;

export const THEME_LABELS: Record<WeightKey, string> = {
  shop: "買い物（スーパーが近い）", med: "病院（診療所・病院が近い）", quiet: "静かさ（車や電車の音が小さい）",
  commute: "通学（大学が近い）", safety: "浸水しにくさ", crime: "防犯（街頭犯罪が少ない）",
  food: "飲食店（近くて多い）", conv: "コンビニが近い", bus: "バス停が近い",
};

export const QUESTIONS: Record<string, { q: string; options: Record<string, string> }> = {
  meal: { q: "ごはんはどうすることが多そう？", options: { cook: "自炊が多い", out: "外食やコンビニが多い", mix: "半々くらい" } },
  commute: { q: "大学へはどうやって通う？", options: { walk: "歩いて", bike: "自転車で", bus: "バスや電車で" } },
  night: { q: "夜はどう過ごしそう？", options: { quiet: "静かじゃないと眠れない", late: "夜ふかしが多め", any: "どちらでもない" } },
  worry: { q: "家族がいちばん心配していることは？", options: { crime: "防犯", disaster: "災害", money: "お金", none: "特にない" } },
  health: { q: "病院にはよく行く？", options: { often: "よく行く・持病がある", sometimes: "ときどき", rarely: "ほとんど行かない" } },
};

export type Answers = Partial<Record<keyof typeof QUESTIONS, string>>;

// 選んだ答えが決まった選択肢かを確かめる（合わないものは捨てる）
export function cleanAnswers(v: unknown): Answers | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const out: Answers = {};
  for (const [q, a] of Object.entries(v as Record<string, unknown>)) {
    if (QUESTIONS[q] && typeof a === "string" && a in QUESTIONS[q].options) out[q] = a;
  }
  return Object.keys(out).length ? out : null;
}

export function cleanWeights(v: unknown): Weights | null {
  if (!v || typeof v !== "object") return null;
  const out = {} as Weights;
  for (const k of WEIGHT_KEYS) {
    const n = (v as Record<string, unknown>)[k];
    if (n !== 0 && n !== 1 && n !== 3) return null;
    out[k] = n;
  }
  return out;
}
