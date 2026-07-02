// Khối hoá đơn — bảng sản phẩm, chế độ sửa (sl/giá/xoá/thêm dòng) →
// POST /api/order/invoice/update (cần mạng, không queue — RMW blob).
import { useState } from "preact/hooks";
import { postJSON } from "../api";
import { invoiceTotal, money, parseMoney } from "../format";

export function InvoiceBlock({ threadId, invoice, onChanged }: { threadId: string; invoice: any[]; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  const startEdit = () => {
    setRows(invoice.map((it) => ({ ...it })));
    setEditing(true);
  };

  const setRow = (i: number, field: string, value: any) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)));
  };

  const save = async () => {
    setBusy(true);
    try {
      const cleaned = rows.filter((r) => (r.sp || "").trim());
      await postJSON("/api/order/invoice/update", { thread_id: Number(threadId), invoice: cleaned });
      setEditing(false);
      onChanged();
    } catch (ex: any) {
      alert(ex.message);
    } finally {
      setBusy(false);
    }
  };

  const list = editing ? rows : invoice;
  return (
    <div class="card">
      <div class="row space">
        <b>Hoá đơn ({invoice.length} món)</b>
        {!editing && <button class="btn small" onClick={startEdit}>Sửa</button>}
      </div>
      <table class="invoice-table">
        <thead>
          <tr><th>SP</th><th>SL</th><th>Giá</th><th>Tiền</th>{editing && <th />}</tr>
        </thead>
        <tbody>
          {list.map((it, i) => (
            <tr key={i}>
              <td>
                {editing ? <input value={it.sp} onInput={(e: any) => setRow(i, "sp", e.target.value)} /> : it.sp}
                {!editing && it.note ? <div class="muted small">{it.note}</div> : null}
              </td>
              <td class="num">
                {editing ? (
                  <input class="narrow" inputMode="numeric" value={it.sl} onInput={(e: any) => setRow(i, "sl", parseMoney(e.target.value))} />
                ) : (
                  it.sl ?? it.quantity
                )}
              </td>
              <td class="num">
                {editing ? (
                  <input class="narrow" inputMode="numeric" value={it.price} onInput={(e: any) => setRow(i, "price", parseMoney(e.target.value))} />
                ) : (
                  money(it.price)
                )}
              </td>
              <td class="num">{money((parseInt(it.price, 10) || 0) * (parseInt(it.sl ?? it.quantity, 10) || 0))}</td>
              {editing && (
                <td>
                  <button class="btn small danger" onClick={() => setRows((p) => p.filter((_, idx) => idx !== i))}>✕</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr><td colSpan={3}><b>Tổng</b></td><td class="num"><b>{money(invoiceTotal(list))}</b></td>{editing && <td />}</tr>
        </tfoot>
      </table>
      {editing && (
        <div class="row">
          <button class="btn" onClick={() => setRows((p) => [...p, { sp: "", sl: 1, price: 0 }])}>+ Thêm dòng</button>
          <button class="btn primary" disabled={busy} onClick={save}>{busy ? "Đang lưu…" : "Lưu"}</button>
          <button class="btn" onClick={() => setEditing(false)}>Huỷ</button>
        </div>
      )}
    </div>
  );
}
