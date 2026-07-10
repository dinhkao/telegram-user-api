// Số thùng (#/so-thung) — BẢN ĐỒ 999 SỐ GỌI thùng toàn kho. Mỗi ô = 1 số (001..999):
// xanh = đang dùng (còn hàng), xám gạch = vô hiệu, trắng = trống (cấp phát được),
// viền xanh lá = số sẽ cấp kế tiếp. Bấm ô đang dùng → chi tiết thùng (#/thung/:id).
// Data: callNumbers() → /api/inventory/call-numbers (server_app/inventory_call_map.py).
import { useEffect, useMemo, useState } from "preact/hooks";
import { callNumbers, soVN, type CallMapResult, type CallNumberBox } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Loading, ErrorState } from "../ui/states";

type Filt = "all" | "instock" | "disabled" | "free";

export function CallNumbers() {
  const [data, setData] = useState<CallMapResult | null>(null);
  const [err, setErr] = useState("");
  const [filt, setFilt] = useState<Filt>("all");

  const load = async () => {
    try { setData(await callNumbers()); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải số thùng"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (["resync", "inventory_changed", "box_changed"].includes(e.type)) { clearTimeout(t); t = setTimeout(load, 400); }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  const occ = useMemo(() => {
    const m = new Map<number, CallNumberBox>();
    (data?.occupied || []).forEach((e) => m.set(e.n, e));
    return m;
  }, [data]);

  const head = (
    <div class="cn-head">
      <BackLink fallback="#/kho" />
      <div class="cn-head-t">
        <div class="cn-head-title">Số thùng</div>
        <div class="cn-head-sub">999 số gọi toàn kho</div>
      </div>
    </div>
  );
  if (err) return <div class="cn-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!data) return <div class="cn-page">{head}<Loading /></div>;

  const c = data.counts;
  const statusOf = (n: number): "instock" | "disabled" | "free" => {
    const e = occ.get(n);
    return e ? (e.disabled ? "disabled" : "instock") : "free";
  };
  const FILTS: { k: Filt; label: string; n: number }[] = [
    { k: "all", label: "Tất cả", n: 999 },
    { k: "instock", label: "Đang dùng", n: c.in_stock || 0 },
    { k: "disabled", label: "Vô hiệu", n: c.disabled || 0 },
    { k: "free", label: "Trống", n: c.free || 0 },
  ];
  const cells: number[] = [];
  for (let n = 1; n <= 999; n++) { const s = statusOf(n); if (filt === "all" || filt === s) cells.push(n); }

  return (
    <div class="cn-page">
      {head}

      <div class="cn-stats">
        <span class="cn-stat"><b>{c.occupied}</b> đang chiếm</span>
        <span class="cn-stat ok"><b>{c.free}</b> trống</span>
        {c.disabled > 0 && <span class="cn-stat off"><b>{c.disabled}</b> vô hiệu</span>}
        {data.next != null && <span class="cn-next">Số kế tiếp: <b>{String(data.next).padStart(3, "0")}</b></span>}
      </div>

      <div class="cn-filters">
        {FILTS.map((f) => (
          <button key={f.k} class={"cn-filter" + (filt === f.k ? " on" : "")} onClick={() => setFilt(f.k)}>
            {f.label} <span class="cn-filter-n">{f.n}</span>
          </button>
        ))}
      </div>

      <div class="cn-legend">
        <span><i class="cn-dot instock" /> đang dùng</span>
        <span><i class="cn-dot free" /> trống</span>
        {c.disabled > 0 && <span><i class="cn-dot disabled" /> vô hiệu</span>}
        <span><i class="cn-dot next" /> kế tiếp</span>
      </div>

      {cells.length === 0 ? (
        <div class="cn-empty">Không có số nào ở nhóm này.</div>
      ) : (
        <div class="cn-grid">
          {cells.map((n) => {
            const e = occ.get(n);
            const isNext = data.next === n;
            const code = String(n).padStart(3, "0");
            const cls = "cn-cell " + statusOf(n) + (isNext ? " next" : "");
            if (e) {
              const st = e.disabled ? "vô hiệu" : `còn ${soVN(e.remaining)}`;
              const title = `${e.product_code}${e.product_name ? " " + e.product_name : ""} · ${st}${e.place_name ? " · " + e.place_name : ""}`;
              return <a key={n} class={cls} href={`#/thung/${e.box_id}`} title={title}>{code}</a>;
            }
            return <div key={n} class={cls} title={isNext ? "trống · sẽ cấp kế tiếp" : "trống"}>{code}</div>;
          })}
        </div>
      )}
    </div>
  );
}
