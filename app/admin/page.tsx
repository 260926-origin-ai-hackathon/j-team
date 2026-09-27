"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

// 物件の掲載情報の管理画面（不動産会社・管理者向け）
// 周辺の計算（道のり・騒音・ハザード）は data/area.json のまま。ここで変えられるのは掲載情報だけ
type Base = { id: string; name: string; rent: number; fee: number; deposit: number; key: number; layout: string; size: number; structure: string };
type Listing = { name: string | null; rent: number | null; fee: number | null; deposit: number | null; key: number | null; published: boolean; updatedAt?: string };
type Me = { backend: boolean; user: { username: string; role: string } | null };
type Draft = { name: string; rent: string; fee: string; deposit: string; key: string; published: boolean };

const C = { accent: "#2A7AB8", deep: "#1E5F8A", soft: "#E3F4FC", line: "#d8e3ea", muted: "#5f6f7a", bad: "#c8412f", good: "#2f9e5b" };
const yen = (n: number) => `${n.toLocaleString("ja-JP")}円`;

function toDraft(b: Base, l?: Listing): Draft {
  return {
    name: l?.name ?? "", rent: l?.rent?.toString() ?? "", fee: l?.fee?.toString() ?? "",
    deposit: l?.deposit?.toString() ?? "", key: l?.key?.toString() ?? "", published: l ? l.published : true,
  };
}

export default function AdminPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [base, setBase] = useState<Base[]>([]);
  const [listings, setListings] = useState<Record<string, Listing>>({});
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [status, setStatus] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState("");

  async function load() {
    const [m, area, l] = await Promise.all([
      fetch("/api/me", { cache: "no-store" }).then((r) => r.json()),
      fetch("/data/area.json").then((r) => r.json()),
      fetch("/api/listings", { cache: "no-store" }).then((r) => r.json()),
    ]);
    setMe(m);
    setBase(area.properties);
    setListings(l.listings || {});
    setDrafts(Object.fromEntries(area.properties.map((p: Base) => [p.id, toDraft(p, l.listings?.[p.id])])));
  }
  useEffect(() => { load().catch(() => setMe({ backend: false, user: null })); }, []);

  const rows = useMemo(() => base.filter((p) => !filter || p.name.includes(filter) || (listings[p.id]?.name || "").includes(filter) || p.id.includes(filter)), [base, listings, filter]);

  async function save(p: Base) {
    const d = drafts[p.id];
    setStatus((s) => ({ ...s, [p.id]: "保存しています…" }));
    const r = await fetch("/api/admin/listings", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ propertyId: p.id, name: d.name, rent: d.rent, fee: d.fee, deposit: d.deposit, key: d.key, published: d.published }),
    });
    const err = r.ok ? "" : ((await r.json().catch(() => ({})))?.error || "error");
    setStatus((s) => ({ ...s, [p.id]: r.ok ? "保存しました" : err === "bad_value" ? "数字を確かめてください（敷金・礼金は0.5か月刻み）" : "保存できませんでした" }));
    if (r.ok) await load();
  }
  async function reset(p: Base) {
    const r = await fetch(`/api/admin/listings?propertyId=${encodeURIComponent(p.id)}`, { method: "DELETE" });
    setStatus((s) => ({ ...s, [p.id]: r.ok ? "元のデータに戻しました" : "戻せませんでした" }));
    if (r.ok) await load();
  }
  const set = (id: string, k: keyof Draft, v: string | boolean) => setDrafts((ds) => ({ ...ds, [id]: { ...ds[id], [k]: v } }));

  const wrap: CSSProperties = { position: "fixed", inset: 0, overflow: "auto", background: "var(--bg, #f6fafc)", color: "var(--ink, #1b2521)", padding: "20px 16px 40px", fontFamily: "var(--body)" };
  const box: CSSProperties = { maxWidth: 1180, margin: "0 auto", display: "grid", gap: 14 };
  const card: CSSProperties = { background: "var(--surface, #fff)", border: `1px solid ${C.line}`, borderRadius: 14, padding: 16 };
  const input: CSSProperties = { font: "inherit", fontSize: 13.5, padding: "5px 8px", border: `1px solid ${C.line}`, borderRadius: 8, width: "100%", background: "var(--surface-2, #f4f8fa)", color: "inherit" };
  const btn = (primary: boolean): CSSProperties => ({ font: "inherit", fontSize: 13, fontWeight: 700, padding: "5px 12px", borderRadius: 8, cursor: "pointer", border: `1px solid ${C.accent}`, background: primary ? C.accent : "transparent", color: primary ? "#fff" : C.accent, whiteSpace: "nowrap" });

  const header = (
    <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
      <a href="/" style={{ color: C.accent, fontWeight: 700, textDecoration: "none" }}>← ヘヤカルテに戻る</a>
      <h1 style={{ fontSize: 22, fontWeight: 900, margin: 0, fontFamily: "var(--display)" }}>物件の掲載情報の管理</h1>
      {me?.user && <span style={{ marginLeft: "auto", fontSize: 13, color: C.muted }}>{me.user.username}（{me.user.role === "admin" ? "管理者" : "一般"}）でログイン中</span>}
    </div>
  );

  if (!me) return <div style={wrap}><div style={box}>{header}<p>読み込んでいます…</p></div></div>;
  if (!me.backend) return <div style={wrap}><div style={box}>{header}<div style={card}>この環境ではデータベースが設定されていないので、管理画面は使えません（README の「バックエンド」を参照）。</div></div></div>;
  if (me.user?.role !== "admin") return (
    <div style={wrap}><div style={box}>{header}
      <div style={card}>管理者だけが開ける画面です。{me.user ? "このユーザーには管理者の権限がありません。" : <>ヘヤカルテの右上の「ログイン」から、管理者のユーザーでログインしてください。</>}</div>
    </div></div>
  );

  return (
    <div style={wrap}><div style={box}>
      {header}
      <div style={{ ...card, fontSize: 13.5, color: C.muted, lineHeight: 1.7 }}>
        家賃・管理費・敷金・礼金・物件名を変えたり、満室の物件を「掲載しない」にしたりできます。空欄の項目は元のデータのままです。
        保存するとすぐにヘヤカルテの地図とお気に入りに反映されます（「掲載しない」にした物件は地図から消え、お気に入りでは「満室」と表示）。
        道のり・騒音・ハザードなどの周辺の情報は変わりません。物件そのものを増やすときは、周辺の計算が必要なので <code>scripts/build_area.py</code> に追加してください。
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input style={{ ...input, maxWidth: 280 }} placeholder="物件名・IDで絞り込む" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <span style={{ fontSize: 13, color: C.muted }}>{rows.length}件／全{base.length}件・掲載しない {Object.values(listings).filter((l) => !l.published).length}件</span>
      </div>
      <div style={{ ...card, padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5, minWidth: 980 }}>
          <thead>
            <tr style={{ background: C.soft, color: C.deep, textAlign: "left" }}>
              {["物件", "物件名（変えるとき）", "家賃（円）", "管理費（円）", "敷金（か月）", "礼金（か月）", "掲載", ""].map((h) => <th key={h} style={{ padding: "10px 8px", fontWeight: 700, whiteSpace: "nowrap" }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const d = drafts[p.id], l = listings[p.id];
              if (!d) return null;
              return (
                <tr key={p.id} style={{ borderTop: `1px solid ${C.line}`, verticalAlign: "top", opacity: d.published ? 1 : 0.65 }}>
                  <td style={{ padding: "8px", minWidth: 190 }}>
                    <b>{l?.name || p.name}</b>
                    <div style={{ fontSize: 12, color: C.muted }}>{p.id}・{p.layout}・{p.size}㎡・{p.structure}</div>
                    <div style={{ fontSize: 12, color: C.muted }}>元のデータ：{yen(p.rent)}＋{yen(p.fee)}・敷{p.deposit} 礼{p.key}</div>
                    {l?.updatedAt && <div style={{ fontSize: 11.5, color: C.accent }}>変更あり（{new Date(l.updatedAt).toLocaleString("ja-JP")}）</div>}
                  </td>
                  <td style={{ padding: 8 }}><input style={input} value={d.name} placeholder={p.name} maxLength={60} onChange={(e) => set(p.id, "name", e.target.value)} /></td>
                  <td style={{ padding: 8, width: 110 }}><input style={input} inputMode="numeric" value={d.rent} placeholder={String(p.rent)} onChange={(e) => set(p.id, "rent", e.target.value)} /></td>
                  <td style={{ padding: 8, width: 100 }}><input style={input} inputMode="numeric" value={d.fee} placeholder={String(p.fee)} onChange={(e) => set(p.id, "fee", e.target.value)} /></td>
                  <td style={{ padding: 8, width: 80 }}><input style={input} inputMode="decimal" value={d.deposit} placeholder={String(p.deposit)} onChange={(e) => set(p.id, "deposit", e.target.value)} /></td>
                  <td style={{ padding: 8, width: 80 }}><input style={input} inputMode="decimal" value={d.key} placeholder={String(p.key)} onChange={(e) => set(p.id, "key", e.target.value)} /></td>
                  <td style={{ padding: 8, whiteSpace: "nowrap" }}>
                    <label style={{ display: "inline-flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
                      <input type="checkbox" checked={d.published} onChange={(e) => set(p.id, "published", e.target.checked)} />{d.published ? "掲載する" : "掲載しない（満室）"}
                    </label>
                  </td>
                  <td style={{ padding: 8, whiteSpace: "nowrap" }}>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button style={btn(true)} onClick={() => save(p)}>保存</button>
                      {l && <button style={btn(false)} onClick={() => reset(p)}>元に戻す</button>}
                    </div>
                    <div style={{ fontSize: 12, marginTop: 4, color: (status[p.id] || "").includes("でき") || (status[p.id] || "").includes("確かめ") ? C.bad : C.good }}>{status[p.id] || ""}</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div></div>
  );
}
