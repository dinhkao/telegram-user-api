// Chi tiết 1 bảng giá chung (#/bang-gia/:id) — XEM giá (lọc theo mã SP), sửa giá
// TỪNG dòng (bấm ✏️ → nhập giá → lưu, backend tự ghi 1 dòng lịch sử cho SP đó),
// xem khách đang dùng + lịch sử đổi giá. API: getPriceList / savePriceOne /
// getPriceHistory.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getPriceList, savePriceOne, getPriceHistory, type PriceListFull, type PriceHistoryRow } from "../api";
import { money } from "../format";
import { onRealtime } from "../realtime";

function fmtMs(ms: number): string {
  try { return new Date(ms).toLocaleString("vi-VN"); } catch { return String(ms); }
}
function priceLabel(p: number | null): string {
  return p == null ? "—" : `${money(p)}đ`;
}

export function PriceListDetail({ listId }: { listId: string }) {
  const [list, setList] = useState<PriceListFull | null>(null);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");
  const [editSp, setEditSp] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<PriceHistoryRow[] | null>(null);
  const [histSp, setHistSp] = useState<string | null>(null);

  const reload = () => getPriceList(listId).then(setList).catch((e) => setErr(e.message));

  useEffect(() => {
    reload();
  }, [listId]);

  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync") {
        clearTimeout(t);
        t = setTimeout(reload, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [listId]);

  const startEdit = (sp: string, price: number) => { setEditSp(sp); setEditVal(String(price)); setErr(""); };
  const cancelEdit = () => setEditSp(null);

  const saveEdit = async (sp: string) => {
    setSaving(true); setErr("");
    try {
      const updated = await savePriceOne(listId, sp, parseInt(editVal, 10));
      setList((l) => ({ ...updated, customers: l?.customers || [] }));
      setEditSp(null);
      if (history !== null) loadHistory(histSp); // đang mở lịch sử → làm mới
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  };

  const loadHistory = (sp: string | null) => {
    setHistSp(sp);
    setHistory(null);
    getPriceHistory(listId, sp || undefined).then(setHistory).catch(() => setHistory([]));
  };

  if (err && !list) return <div class="prod-detail"><BackLink fallback="#/bang-gia" /><p class="error">{err}</p></div>;
  if (!list) return <div class="prod-detail"><p class="muted">Đang tải…</p></div>;

  const q = filter.trim().toLowerCase();
  const items = q ? list.items.filter((it) => it.sp.toLowerCase().includes(q)) : list.items;

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/bang-gia" />
        <div>
          <div class="prod-sp">{list.name}</div>
          <div class="muted small">#{list.id} · {list.items.length} SP</div>
        </div>
      </div>

      {err && <p class="error">{err}</p>}

      <section class="card">
        <input class="search" type="search" placeholder="🔍 Tìm mã SP…" value={filter} onInput={(e: any) => setFilter(e.target.value)} />
        <table class="invoice-table">
          <tbody>
            {items.map((it) => (
              <tr key={it.sp}>
                <td>{it.sp}</td>
                {editSp === it.sp ? (
                  <>
                    <td class="num"><input class="num-inp" type="number" inputMode="numeric" value={editVal} autofocus onFocus={(e: any) => e.target.select()} onInput={(e: any) => setEditVal(e.target.value)} /></td>
                    <td>
                      <button class="btn small primary" disabled={saving} onClick={() => saveEdit(it.sp)}>{saving ? "…" : "💾"}</button>
                      <button class="btn small" onClick={cancelEdit}>✕</button>
                    </td>
                  </>
                ) : (
                  <>
                    <td class="num"><b>{money(it.price)}đ</b></td>
                    <td>
                      <button class="btn small" title="Sửa giá" onClick={() => startEdit(it.sp, it.price)}>✏️</button>
                      <button class="btn small" title="Lịch sử SP này" onClick={() => loadHistory(it.sp)}>🕐</button>
                    </td>
                  </>
                )}
              </tr>
            ))}
            {!items.length && <tr><td colSpan={3} class="muted small">{q ? "Không thấy SP khớp." : "Bảng giá trống."}</td></tr>}
          </tbody>
        </table>
      </section>

      <section class="card">
        <div class="row space">
          <label class="card-label">Lịch sử đổi giá {histSp ? `— ${histSp}` : ""}</label>
          <button class="btn small" onClick={() => loadHistory(null)}>Toàn bộ</button>
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
