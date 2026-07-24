// Số thùng (#/so-thung) — BẢN ĐỒ SỐ GỌI thùng toàn kho, 27 block xoay vòng
// (001–999 → A001…Z999 → 001). Mặc định vẽ block 001–999; block chữ chỉ hiện khi
// đã có số được cấp trong block đó (server trả `blocks`). Mỗi ô = 1 số: xanh =
// đang dùng (còn hàng), xám gạch = vô hiệu, trắng = trống (cấp phát được), viền
// xanh lá = số sẽ cấp kế tiếp. Bấm ô đang dùng → chi tiết thùng (#/thung/:id).
// Data: callNumbers() → /api/inventory/call-numbers (server_app/inventory_call_map.py).
import { useEffect, useMemo, useState } from "preact/hooks";
import { callNumbers, soVN, type CallMapResult, type CallNumberBox } from "../api";
import { onRealtime } from "../realtime";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";

type Filt = "all" | "instock" | "disabled" | "free";
// Field mới của API (blocks/next_code) chưa có trong api.ts — mở rộng type tại chỗ.
type CallMapX = CallMapResult & { blocks?: string[]; next_code?: string | null };

/** Mã hiển thị của số gọi — khớp inventory_store.domain.call_code: 47 → "047", 1046 → "A047". */
function codeOf(n: number): string {
  if (n > 999) {
    const block = Math.floor((n - 1) / 999);
    const pos = ((n - 1) % 999) + 1;
    return String.fromCharCode(64 + block) + String(pos).padStart(3, "0");
  }
  return String(n).padStart(3, "0");
}
/** Số gọi đầu block − 1: "" → 0 (001–999); "A" → 999 (A001 = 1000). */
const blockBase = (b: string): number => (b ? (b.charCodeAt(0) - 64) * 999 : 0);

export function CallNumbers() {
  const [data, setData] = useState<CallMapX | null>(null);
  const [err, setErr] = useState("");
  const [filt, setFilt] = useState<Filt>("all");

  const load = async () => {
    try { setData((await callNumbers()) as CallMapX); setErr(""); }
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

  const total = data?.total || 999;
  const head = <PageHead fallback="#/kho" title="Số thùng" sub={`${soVN(total)} số gọi toàn kho`} />;
  if (err) return <div class="cn-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!data) return <div class="cn-page">{head}<Loading /></div>;

  const c = data.counts;
  const statusOf = (n: number): "instock" | "disabled" | "free" => {
    const e = occ.get(n);
    return e ? (e.disabled ? "disabled" : "instock") : "free";
  };
  const FILTS: { k: Filt; label: string; n: number }[] = [
    { k: "all", label: "Tất cả", n: total },
    { k: "instock", label: "Đang dùng", n: c.in_stock || 0 },
    { k: "disabled", label: "Vô hiệu", n: c.disabled || 0 },
    { k: "free", label: "Trống", n: c.free || 0 },
  ];
  // Section theo block: "" (001–999) luôn vẽ; block chữ chỉ khi server báo đã có số cấp.
  const blocks = data.blocks && data.blocks.length ? data.blocks : [""];
  const sections = blocks.map((b) => {
    const base = blockBase(b);
    const ns: number[] = [];
    for (let i = 1; i <= 999; i++) { const n = base + i; const s = statusOf(n); if (filt === "all" || filt === s) ns.push(n); }
    return { b, ns };
  });
  const anyCell = sections.some((s) => s.ns.length > 0);
  const nextCode = data.next != null ? (data.next_code || codeOf(data.next)) : null;

  return (
    <div class="cn-page">
      {head}

      <div class="cn-stats">
        <span class="cn-stat"><b>{c.occupied}</b> đang chiếm</span>
        <span class="cn-stat ok"><b>{c.free}</b> trống</span>
        {c.disabled > 0 && <span class="cn-stat off"><b>{c.disabled}</b> vô hiệu</span>}
        {nextCode != null && <span class="cn-next">Số kế tiếp: <b>{nextCode}</b></span>}
      </div>

      <div class="chips cn-filters">
        {FILTS.map((f) => (
          <button key={f.k} class={"chip" + (filt === f.k ? " active" : "")} onClick={() => setFilt(f.k)}>
            {f.label} <span class="chip-n">{f.n}</span>
          </button>
        ))}
      </div>

      <div class="cn-legend">
        <span><i class="cn-dot instock" /> đang dùng</span>
        <span><i class="cn-dot free" /> trống</span>
        {c.disabled > 0 && <span><i class="cn-dot disabled" /> vô hiệu</span>}
        <span><i class="cn-dot next" /> kế tiếp</span>
      </div>

      {!anyCell ? (
        <EmptyState>Không có số nào ở nhóm này.</EmptyState>
      ) : (
        sections.filter((s) => s.ns.length > 0).map((s) => (
          <div key={s.b || "0"}>
            {s.b !== "" && (
              <div class="cn-block-h">
                Block {s.b} · {s.b}001–{s.b}999
              </div>
            )}
            <div class="cn-grid">
              {s.ns.map((n) => {
                const e = occ.get(n);
                const isNext = data.next === n;
                const code = codeOf(n);
                const cls = "cn-cell " + statusOf(n) + (isNext ? " next" : "");
                if (e) {
                  const st = e.disabled ? "vô hiệu" : `còn ${soVN(e.remaining)}`;
                  const title = `${e.product_code}${e.product_name ? " " + e.product_name : ""} · ${st}${e.place_name ? " · " + e.place_name : ""}`;
                  return <a key={n} class={cls} href={`#/thung/${e.box_id}`} title={title}>{code}</a>;
                }
                return <div key={n} class={cls} title={isNext ? "trống · sẽ cấp kế tiếp" : "trống"}>{code}</div>;
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
