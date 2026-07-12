// Trình NHẬP hoá đơn — thuần chỉnh sửa, dùng cho trang Sửa hoá đơn
// (OrderInvoiceEdit) và tab Nâng cao trang tạo đơn (CreateOrder, createMode).
// Dòng SP có autocomplete + tự lấy giá theo khách (/api/customer/price),
// Thêm nhanh bằng text, điều chỉnh Chiết khấu/PVC/VAT, tổng sống.
// KHÔNG còn chế độ xem / nút HĐ KiotViet — phần đó nằm ở khối Hoá đơn của
// OrderDetail. Parent quyết định onSave làm gì và điều hướng sau khi lưu.
import { useEffect, useRef, useState } from "preact/hooks";
import { fetchCustomerPrice, previewOrder, searchProducts, type PriceInfo, type OrderPreview } from "../api";
import { money, parseMoney } from "../format";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PickerPopup } from "../ui/PickerPopup";

export type EditorRow = { sp: string; sl: number; price: number; note?: string };
export type EditorPayload = { invoice: EditorRow[]; discount: number; pvc: number; vat: number };

// ── Ô nhập mã SP + gợi ý (autocomplete) — popup neo đỉnh, cho mã tự do ────────
function ProductInput({ value, onChange, onCommit }: {
  value: string;
  onChange: (code: string) => void;      // cập nhật mã (cho phép mã tự do)
  onCommit: (code: string) => void;      // chọn gợi ý → parent lấy giá
}) {
  return (
    <PickerPopup
      value={value}
      placeholder="Mã SP"
      allowFreeText
      class="ie-sp"
      onSearch={async (v) => {
        const r = await searchProducts(v).catch(() => []);
        // chỉ gợi ý SP "có thể bán" (cờ ở chi tiết SP); mã tự do vẫn gõ được
        return r.filter((s) => s.can_sell !== false)
          .map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }));
      }}
      onPick={(o) => { onChange(o.key); onCommit(o.key); }}
    />
  );
}

export function InvoiceEditor({ customerId, invoice, discount, pvc, vat, onSave, onCancel, createMode }: {
  customerId?: string;
  invoice: any[];
  discount?: number; pvc?: number; vat?: number;
  onSave: (payload: EditorPayload) => Promise<void> | void;
  onCancel?: () => void;   // trang sửa: Huỷ → quay về chi tiết; createMode không cần
  createMode?: boolean;    // form tạo đơn → nhãn nút "Lưu & tạo đơn"
}) {
  const [rows, setRows] = useState<EditorRow[]>([]);
  const [disc, setDisc] = useState(0);
  const [p, setP] = useState(0);
  const [v, setV] = useState(0);
  const [busy, setBusy] = useState(false);
  const [quickText, setQuickText] = useState("");
  const [quickMsg, setQuickMsg] = useState("");
  const [quickPreview, setQuickPreview] = useState<OrderPreview | null>(null);
  const quickSeq = useRef(0);

  // Xem trước tức thời khi gõ ở ô Thêm nhanh (giá theo khách của đơn)
  useEffect(() => {
    const t = quickText.trim();
    if (!t) { setQuickPreview(null); setQuickMsg(""); return; }
    const my = ++quickSeq.current;
    previewOrder(t, customerId)
      .then((r) => {
        if (my !== quickSeq.current) return;
        setQuickPreview(r);
        const parsed = (r.invoice || []).map((it) => ({
          sp: (it.sp || "").trim(), sl: Number(it.sl) || 0,
          price: Number(it.price) || 0, note: "",
        })).filter((it) => it.sp);
        if (!parsed.length) { setQuickMsg("Chưa nhận ra sản phẩm nào."); return; }
        setRows((prev) => {
          const next = [...prev];
          for (const item of parsed) {
            const key = item.sp.toUpperCase();
            const idx = next.findIndex((row) => (row.sp || "").trim().toUpperCase() === key);
            if (idx >= 0) next[idx] = { ...next[idx], sp: item.sp, sl: item.sl, price: item.price };
            else next.push(item);
          }
          return next;
        });
        setQuickMsg(`✓ Đã tự cập nhật ${parsed.length} món`);
      })
      .catch(() => {
        if (my === quickSeq.current) { setQuickPreview(null); setQuickMsg("Lỗi phân tích"); }
      });
  }, [quickText, customerId]);
  // Giá + bảng giá theo mã SP (đã hoa) — để ghi rõ giá lấy từ bảng giá nào
  const [listPrices, setListPrices] = useState<Record<string, PriceInfo>>({});
  const listRef = useRef<Record<string, PriceInfo>>({});

  // Tra 1 lần giá bảng cho 1 mã (cache trong listRef); trả PriceInfo
  const loadListPrice = async (code: string): Promise<PriceInfo> => {
    const key = (code || "").trim().toUpperCase();
    const empty: PriceInfo = { price: 0, source: null, list_name: null };
    if (!key || !customerId) return empty;
    if (key in listRef.current) return listRef.current[key];
    const info = await fetchCustomerPrice(customerId, key).catch(() => empty);
    listRef.current = { ...listRef.current, [key]: info };
    setListPrices(listRef.current);
    return info;
  };

  // Chỉ nạp lại rows khi NỘI DUNG invoice đổi thật — không nạp lại khi reload nền
  // (realtime) trả về invoice y hệt, để không xoá phần user đang sửa dở.
  const seededSig = useRef<string>("__init__");
  useEffect(() => {
    const sig = JSON.stringify((invoice || []).map((it) => [it.sp, it.sl ?? it.quantity, it.price, it.note]));
    if (sig === seededSig.current) return;
    seededSig.current = sig;
    setRows((invoice || []).map((it) => ({
      sp: it.sp || "", sl: Number(it.sl ?? it.quantity ?? 0) || 0,
      price: Number(it.price) || 0, note: it.note || "",
    })));
  }, [invoice]);
  // Nạp trước giá bảng cho các mã có sẵn (đơn đang mở) để chú thích hiện ngay
  useEffect(() => {
    if (!customerId) return;
    const codes = [...new Set((invoice || []).map((it) => (it.sp || "").trim().toUpperCase()).filter(Boolean))];
    codes.forEach((c) => loadListPrice(c));
  }, [invoice, customerId]);
  useEffect(() => setDisc(Number(discount) || 0), [discount]);
  useEffect(() => setP(Number(pvc) || 0), [pvc]);
  useEffect(() => setV(Number(vat) || 0), [vat]);

  const tienHang = rows.reduce((s, r) => s + (r.price || 0) * (r.sl || 0), 0);
  const tong = tienHang - disc + p + v;

  const setRow = (i: number, f: string, val: any) => setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [f]: val } : r)));
  const addRow = () => setRows((prev) => [...prev, { sp: "", sl: 1, price: 0, note: "" }]);
  const removeRow = (i: number) => setRows((prev) => prev.filter((_, idx) => idx !== i));

  // Tự lấy giá theo khách khi chốt mã SP — chỉ điền khi giá đang trống (không đè giá tay)
  const autoPrice = async (i: number, code: string) => {
    if (!customerId || !code.trim()) return;
    const { price } = await loadListPrice(code);
    if (price) setRows((prev) => prev.map((r, idx) => (idx === i && !r.price ? { ...r, price } : r)));
  };

  const save = async () => {
    setBusy(true);
    try { await onSave({ invoice: rows.filter((r) => (r.sp || "").trim()), discount: disc, pvc: p, vat: v }); }
    catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(false); }
  };

  const priceTag = (sp: string, price: number) => {
    const info = listPrices[(sp || "").trim().toUpperCase()];
    if (!info || !info.price) return null;
    const name = info.list_name || "bảng giá";
    return Number(price) === info.price
      ? <span class="pricetag ok">✓ {name}</span>
      : <span class="pricetag">{name}: {money(info.price)}</span>;
  };

  // ── Chỉnh sửa — mỗi món là 1 khối, canh gọn trên mobile ─────────────────
  return (
    <div class="card">
      <div class="row space">
        <b>Sản phẩm ({rows.length} món)</b>
      </div>
      <div class="inv-edit">
        {rows.map((it, i) => (
          <div class="edit-row" key={i}>
            <div class="edit-top">
              <ProductInput value={it.sp} onChange={(c) => setRow(i, "sp", c)} onCommit={(c) => autoPrice(i, c)} />
              <button class="btn small danger" onClick={() => removeRow(i)}><Icon name="close" size={16} /></button>
            </div>
            <div class="edit-mid">
              <label class="fld sl">SL<input inputMode="numeric" value={it.sl} onInput={(e: any) => setRow(i, "sl", parseMoney(e.target.value))} /></label>
              <span class="times">×</span>
              <label class="fld price">Giá<input inputMode="numeric" value={it.price} onInput={(e: any) => setRow(i, "price", parseMoney(e.target.value))} /></label>
              {(() => {
                const info = listPrices[(it.sp || "").trim().toUpperCase()];
                return info && info.price && Number(it.price) !== info.price ? (
                  <button type="button" class="price-reset" title={`Đặt lại giá bảng: ${money(info.price)}`}
                    onClick={() => setRow(i, "price", info.price)}>
                    <Icon name="refresh" size={15} />
                  </button>
                ) : null;
              })()}
              <span class="eq">= <b>{money((it.price || 0) * (it.sl || 0))}</b></span>
            </div>
            <div class="edit-bot">
              {priceTag(it.sp, it.price)}
              <input class="note-inp" placeholder="ghi chú" value={it.note || ""} onInput={(e: any) => setRow(i, "note", e.target.value)} />
            </div>
          </div>
        ))}
      </div>
      <button class="btn wide" onClick={addRow}><Icon name="plus" size={16} /> Thêm dòng</button>

      {/* Thêm nhanh bằng text — như tab Nhanh ở trang tạo đơn (kèm xem trước + gợi ý) */}
      <div class="quick-add">
        {/* Xem trước Ở TRÊN ô nhập → bàn phím mobile không che */}
        {quickText.trim() && quickPreview && (
          quickPreview.invoice.length ? (
            <table class="invoice-table">
              <tbody>
                {quickPreview.invoice.map((it, i) => (
                  <tr key={i}>
                    <td>{it.sp}</td>
                    <td class="num">x{it.sl}</td>
                    <td class="num">
                      {money(it.price)}
                      {it.list_price != null && it.list_price > 0 && it.list_price !== it.price && (
                        <div class="old-price">{money(it.list_price)}</div>
                      )}
                    </td>
                    <td class="num"><b>{money(it.sub)}</b></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td colSpan={3}>Tổng thêm</td><td class="num"><b class="money">{money(quickPreview.total)}</b></td></tr>
              </tfoot>
            </table>
          ) : (
            <p class="muted small">Chưa nhận ra sản phẩm nào — kiểm tra mã SP.</p>
          )
        )}

        <textarea
          rows={2}
          placeholder={"⚡ Thêm nhanh (dán nhiều dòng): vd\nK2L 10\nKDDT 5t"}
          value={quickText}
          onInput={(e: any) => setQuickText(e.target.value)}
        />
        {quickMsg && <div class="muted small">{quickMsg}</div>}
        <div class="muted small hint">
          💡 <code>&lt;mã SP&gt; &lt;SL&gt;</code> (mã trước, SL sau) · <code>5t</code>=5 thùng, <code>3b</code>=3 bịch, đổi số/đơn vị bằng <code>5t 60</code>/<code>3b 12</code>.
          {" "}Mặc định số/thùng: 50 (DM50 100; KDXDB/KGL/KMT/KMD/KHDX 5; KDDT 12) · số/bịch: 10 (KDDT 3) · DM180 1 lốc 12.
          {" "}Giá: nhập số sau SL để ghi đè (<code>K2L 10 25000</code>).
        </div>
      </div>

      <div class="adj">
        <label>Tiền hàng<b class="num">{money(tienHang)}</b></label>
        <label>Chiết khấu<input class="narrow" inputMode="numeric" value={disc} onInput={(e: any) => setDisc(parseMoney(e.target.value))} /></label>
        <label>PVC (ship)<input class="narrow" inputMode="numeric" value={p} onInput={(e: any) => setP(parseMoney(e.target.value))} /></label>
        <label>VAT
          <span class="row">
            <input class="narrow" inputMode="numeric" value={v} onInput={(e: any) => setV(parseMoney(e.target.value))} />
            <button class="btn small" onClick={() => setV(Math.round(tienHang * 0.08))}>8%</button>
          </span>
        </label>
        <div class="row space total"><b>Tổng thanh toán</b><b class="money">{money(tong)}</b></div>
      </div>

      <div class="row ie-actions">
        <button class="btn primary" disabled={busy} onClick={save}>{busy ? "Đang lưu…" : createMode ? <><Icon name="save" size={16} /> Lưu &amp; tạo đơn</> : <><Icon name="save" size={16} /> Lưu</>}</button>
        {onCancel && <button class="btn" disabled={busy} onClick={onCancel}>Huỷ</button>}
      </div>
    </div>
  );
}
