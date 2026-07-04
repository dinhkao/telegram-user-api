// Chi tiết 1 bảng giá chung (#/bang-gia/:id) — sửa giá (thêm/sửa/xoá) → lưu
// (backend diff → lịch sử mỗi SP đổi), xem khách đang dùng, xem lịch sử đổi giá
// (cả bảng hoặc lọc 1 SP). API: getPriceList / savePriceList / getPriceHistory.
import { useEffect, useState } from "preact/hooks";
import { getPriceList, savePriceList, getPriceHistory, type PriceListFull, type PriceHistoryRow } from "../api";
import { money } from "../format";

type Row = { sp: string; price: string };

function fmtMs(ms: number): string {
  try { return new Date(ms).toLocaleString("vi-VN"); } catch { return String(ms); }
}
function priceLabel(p: number | null): string {
  return p == null ? "—" : `${money(p)}đ`;
}

export function PriceListDetail({ listId }: { listId: string }) {
  const [list, setList] = useState<PriceListFull | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<PriceHistoryRow[] | null>(null);
  const [histSp, setHistSp] = useState<string | null>(null);

  const hydrate = (l: PriceListFull) => {
    setList(l);
    setRows(l.items.map((it) => ({ sp: it.sp, price: String(it.price) })));
  };

  useEffect(() => {
    getPriceList(listId).then(hydrate).catch((e) => setErr(e.message));
  }, [listId]);

  const setRow = (i: number, k: keyof Row, v: string) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const addRow = () => setRows((rs) => [...rs, { sp: "", price: "" }]);
  const delRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i));

  const save = async () => {
    setSaving(true); setErr(""); setMsg("");
    const items = rows
      .map((r) => ({ sp: r.sp.trim(), price: parseInt(r.price, 10) }))
      .filter((it) => it.sp && it.price > 0);
    try {
      hydrate(await savePriceList(listId, items));
      setMsg("✅ Đã lưu — lịch sử đổi giá đã ghi");
      if (history !== null) loadHistory(histSp); // đang mở lịch sử → làm mới
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  };

  const loadHistory = (sp: string | null) => {
    setHistSp(sp);
    setHistory(null);
    getPriceHistory(listId, sp || undefined).then(setHistory).catch(() => setHistory([]));
  };

  if (err && !list) return <div class="prod-detail"><a class="back" href="#/bang-gia">←</a><p class="error">{err}</p></div>;
  if (!list) return <div class="prod-detail"><p class="muted">Đang tải…</p></div>;

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <a class="back" href="#/bang-gia">←</a>
        <div>
          <div class="prod-sp">{list.name}</div>
          <div class="muted small">#{list.id} · {rows.length} SP</div>
        </div>
      </div>

      {msg && <p class="muted small">{msg}</p>}
      {err && <p class="error">{err}</p>}

      <section class="card">
        <label class="card-label">Giá sản phẩm</label>
        <table class="invoice-table">
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><input value={r.sp} placeholder="Mã SP" onInput={(e: any) => setRow(i, "sp", e.target.value)} /></td>
                <td class="num"><input class="num-inp" type="number" inputMode="numeric" value={r.price} placeholder="Giá" onFocus={(e: any) => e.target.select()} onInput={(e: any) => setRow(i, "price", e.target.value)} /></td>
                <td>
                  <button class="btn small" title="Lịch sử SP này" onClick={() => loadHistory(r.sp.trim())}>🕐</button>
                  <button class="btn small" onClick={() => delRow(i)}>✕</button>
                </td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={3} class="muted small">Chưa có SP — thêm dòng.</td></tr>}
          </tbody>
        </table>
        <div class="row">
          <button class="btn small" onClick={addRow}>➕ Thêm SP</button>
          <button class="btn primary" disabled={saving} onClick={save}>{saving ? "Đang lưu…" : "💾 Lưu giá"}</button>
        </div>
      </section>

      <section class="card">
        <div class="row space">
          <label class="card-label">Lịch sử đổi giá {histSp ? `— ${histSp}` : ""}</label>
          <span>
            <button class="btn small" onClick={() => loadHistory(null)}>Toàn bộ</button>
          </span>
        </div>
        {history === null ? (
          <button class="btn small" onClick={() => loadHistory(null)}>Xem lịch sử</button>
        ) : !history.length ? (
          <p class="muted small">Chưa có thay đổi nào.</p>
        ) : (
          <ul class="hist">
            {history.map((h, i) => (
              <li key={i}>
                <b>{h.sp}</b>: {priceLabel(h.old_price)} → {priceLabel(h.new_price)}
                {h.new_price == null && " (xoá)"}{h.old_price == null && " (mới)"}
                <div class="muted small">{h.changed_by || "?"} · {fmtMs(h.changed_at)}</div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section class="card">
        <label class="card-label">Khách đang dùng bảng giá này ({list.customers.length})</label>
        {!list.customers.length ? (
          <p class="muted small">Chưa có khách nào gắn bảng giá này.</p>
        ) : (
          <ul class="order-list">
            {list.customers.map((c) => (
              <li key={c.key}><a class="order-card" href={`#/khach/${encodeURIComponent(c.key)}`}>👤 {c.name} <span class="muted small">· {c.key}</span></a></li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
