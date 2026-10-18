"use client";

import { useEffect, useMemo, useState } from "react";
// 見た目は CSS モジュールで当てる（CSP で style 属性を許さないため、style={...} は使わない）
import s from "./admin.module.css";

// 物件の掲載情報の管理画面（不動産会社・管理者向け）
// 周辺の計算（道のり・騒音・ハザード）は data/area.json のまま。ここで変えられるのは掲載情報だけ
type Base = { id: string; name: string; rent: number; fee: number; deposit: number; key: number; layout: string; size: number; structure: string };
type Listing = { name: string | null; rent: number | null; fee: number | null; deposit: number | null; key: number | null; published: boolean; updatedAt?: string };
type Me = { backend: boolean; user: { username: string; role: string } | null };
type Draft = { name: string; rent: string; fee: string; deposit: string; key: string; published: boolean };

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

  const statusClass = (t: string) => (t.includes("でき") || t.includes("確かめ") ? s.err : s.ok);

  const header = (
    <div className={s.header}>
      <a href="/" className={s.back}>← ヘヤカルテに戻る</a>
      <h1 className={s.title}>物件の掲載情報の管理</h1>
      {me?.user && <span className={s.who}>{me.user.username}（{me.user.role === "admin" ? "管理者" : "一般"}）でログイン中</span>}
    </div>
  );
  const page = (children: React.ReactNode) => <div className={s.wrap}><div className={s.box}>{header}{children}</div></div>;

  if (!me) return page(<p>読み込んでいます…</p>);
  if (!me.backend) return page(<div className={s.card}>この環境ではデータベースが設定されていないので、管理画面は使えません（README の「バックエンド」を参照）。</div>);
  if (me.user?.role !== "admin") return page(
    <div className={s.card}>管理者だけが開ける画面です。{me.user ? "このユーザーには管理者の権限がありません。" : <>ヘヤカルテの右上の「ログイン」から、管理者のユーザーでログインしてください。</>}</div>,
  );

  return page(<>
    <div className={`${s.card} ${s.note}`}>
      家賃・管理費・敷金・礼金・物件名を変えたり、満室の物件を「掲載しない」にしたりできます。空欄の項目は元のデータのままです。
      保存するとすぐにヘヤカルテの地図とお気に入りに反映されます（「掲載しない」にした物件は地図から消え、お気に入りでは「満室」と表示）。
      道のり・騒音・ハザードなどの周辺の情報は変わりません。物件そのものを増やすときは、周辺の計算が必要なので <code>scripts/build_area.py</code> に追加してください。
    </div>
    <div className={s.filterRow}>
      <input className={`${s.input} ${s.filter}`} placeholder="物件名・IDで絞り込む" value={filter} onChange={(e) => setFilter(e.target.value)} />
      <span className={s.count}>{rows.length}件／全{base.length}件・掲載しない {Object.values(listings).filter((l) => !l.published).length}件</span>
    </div>
    <div className={`${s.card} ${s.tableCard}`}>
      <table className={s.table}>
        <thead>
          <tr>{["物件", "物件名（変えるとき）", "家賃（円）", "管理費（円）", "敷金（か月）", "礼金（か月）", "掲載", ""].map((h) => <th key={h}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const d = drafts[p.id], l = listings[p.id];
            if (!d) return null;
            return (
              <tr key={p.id} className={d.published ? undefined : s.off}>
                <td className={s.nameCell}>
                  <b>{l?.name || p.name}</b>
                  <div className={s.sub}>{p.id}・{p.layout}・{p.size}㎡・{p.structure}</div>
                  <div className={s.sub}>元のデータ：{yen(p.rent)}＋{yen(p.fee)}・敷{p.deposit} 礼{p.key}</div>
                  {l?.updatedAt && <div className={s.changed}>変更あり（{new Date(l.updatedAt).toLocaleString("ja-JP")}）</div>}
                </td>
                <td><input className={s.input} value={d.name} placeholder={p.name} maxLength={60} onChange={(e) => set(p.id, "name", e.target.value)} /></td>
                <td className={s.w110}><input className={s.input} inputMode="numeric" value={d.rent} placeholder={String(p.rent)} onChange={(e) => set(p.id, "rent", e.target.value)} /></td>
                <td className={s.w100}><input className={s.input} inputMode="numeric" value={d.fee} placeholder={String(p.fee)} onChange={(e) => set(p.id, "fee", e.target.value)} /></td>
                <td className={s.w80}><input className={s.input} inputMode="decimal" value={d.deposit} placeholder={String(p.deposit)} onChange={(e) => set(p.id, "deposit", e.target.value)} /></td>
                <td className={s.w80}><input className={s.input} inputMode="decimal" value={d.key} placeholder={String(p.key)} onChange={(e) => set(p.id, "key", e.target.value)} /></td>
                <td className={s.nowrap}>
                  <label className={s.check}>
                    <input type="checkbox" checked={d.published} onChange={(e) => set(p.id, "published", e.target.checked)} />{d.published ? "掲載する" : "掲載しない（満室）"}
                  </label>
                </td>
                <td className={s.nowrap}>
                  <div className={s.actions}>
                    <button className={`${s.btn} ${s.primary}`} onClick={() => save(p)}>保存</button>
                    {l && <button className={s.btn} onClick={() => reset(p)}>元に戻す</button>}
                  </div>
                  <div className={`${s.status} ${statusClass(status[p.id] || "")}`}>{status[p.id] || ""}</div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  </>);
}
