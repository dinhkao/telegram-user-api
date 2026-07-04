// Trình nhập hoá đơn nâng cao — dùng chung cho OrderDetail (sửa) và CreateOrder
// (tạo mới). Dòng SP có autocomplete + tự lấy giá theo khách (/api/customer/price),
// điều chỉnh Chiết khấu/PVC/VAT (nút VAT 8%), tổng sống, nút Lưu + Tạo HĐ KiotViet.
// Parent quyết định onSave làm gì (invoice/update hay create-flow) và onCreateInvoice.
import { useEffect, useRef, useState } from "preact/hooks";
import { fetchCustomerPrice, previewOrder, searchProducts, type PriceInfo, type OrderPreview } from "../api";
import { money, parseMoney } from "../format";
import { InvoiceTable } from "./InvoiceTable";
import { toast } from "../ui/feedback";

export type EditorRow = { sp: string; sl: number; price: number; note?: string };
export type EditorPayload = { invoice: EditorRow[]; discount: number; pvc: number; vat: number };

// ── Ô nhập mã SP + gợi ý (autocomplete) ──────────────────────────────────
function ProductInput({ value, onChange, onCommit }: {
  value: string;
  onChange: (code: string) => void;      // gõ tới đâu cập nhật tới đó (cho phép mã tự do)
  onCommit: (code: string) => void;      // chọn gợi ý / rời ô → parent lấy giá
}) {
  const [q, setQ] = useState(value);
  const [sug, setSug] = useState<{ code: string; name: string }[]>([]);
  const [open, setOpen] = useState(false);
  const seq = useRef(0);
  useEffect(() => setQ(value), [value]);

  // Không debounce — gõ/bấm là gọi ngay; seq chặn kết quả cũ đè kết quả mới
  const fetchSug = async (val: string) => {
    const s = ++seq.current;
    const r = await searchProducts(val).catch(() => []);
    if (s !== seq.current) return;
    setSug(r);
    setOpen(r.length > 0);
  };
  const input = (val: string) => { setQ(val); onChange(val); fetchSug(val); };
  const pick = (code: string) => { setQ(code); setOpen(false); setSug([]); onChange(code); onCommit(code); };

  return (
    <div class="ac">
      <input
        value={q}
        placeholder="Mã SP"
        onInput={(e: any) => input(e.target.value)}
        onFocus={() => fetchSug(q)}
        onBlur={() => { setTimeout(() => setOpen(false), 150); onCommit(q); }}
      />
      {open && (
        <ul class="ac-list">
          {sug.map((s) => (
            <li key={s.code} onMouseDown={() => pick(s.code)}>
              <b>{s.code}</b>{s.name ? ` · ${s.name}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function InvoiceEditor({ customerId, invoice, discount, pvc, vat, onSave, onCreateInvoice, canCreate, hasInvoice, createMode, debt, onView, onDelete, onPrint, canDelete, invoiceCode, onRefreshDebt, debtLocked }: {
  customerId?: string;
  invoice: any[];
  discount?: number; pvc?: number; vat?: number;
  onSave: (payload: EditorPayload) => Promise<void> | void;
  onCreateInvoice?: () => Promise<void> | void;
  canCreate?: boolean;                 // chỉ admin mới thấy nút tạo HĐ
  hasInvoice?: boolean;
  createMode?: boolean;   // form tạo đơn → luôn ở chế độ sửa, không có nút xem
  debt?: number | null;                // nợ khách (cho bảng xem, giống dashboard)
  onView?: () => void;                 // xem HĐ KiotViet
  onDelete?: () => Promise<void> | void; // xoá HĐ KiotViet
  onPrint?: () => Promise<void> | void;  // in HĐ + phiếu giao
  canDelete?: boolean;                 // chỉ admin
  invoiceCode?: string | number;
  onRefreshDebt?: () => void;          // kéo nợ KiotViet mới nhất
  debtLocked?: boolean;                // đã tạo HĐ → nợ chốt, không kéo được
}) {
  const [rows, setRows] = useState<EditorRow[]>([]);
  const [disc, setDisc] = useState(0);
  const [p, setP] = useState(0);
  const [v, setV] = useState(0);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(!!createMode);
  const [quickText, setQuickText] = useState("");
  const [quickBusy, setQuickBusy] = useState(false);
  const [quickMsg, setQuickMsg] = useState("");
  const [quickPreview, setQuickPreview] = useState<OrderPreview | null>(null);
  const quickSeq = useRef(0);

  // Xem trước tức thời khi gõ ở ô Thêm nhanh (giá theo khách của đơn)
  useEffect(() => {
    const t = quickText.trim();
    if (!editing || !t) { setQuickPreview(null); return; }
    const my = ++quickSeq.current;
    previewOrder(t, customerId)
      .then((r) => { if (my === quickSeq.current) setQuickPreview(r); })
      .catch(() => { if (my === quickSeq.current) setQuickPreview(null); });
  }, [quickText, customerId, editing]);
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

  // Thêm nhanh: dán text (như tab Nhanh) → parse (giá theo khách) → nối vào danh sách
  const quickAdd = async () => {
    const t = quickText.trim();
    if (!t) return;
    setQuickBusy(true); setQuickMsg("");
    try {
      const r = await previewOrder(t, customerId);
      const add = (r.invoice || []).map((it) => ({ sp: it.sp || "", sl: Number(it.sl) || 0, price: Number(it.price) || 0, note: "" }));
      if (!add.length) { setQuickMsg("Không nhận ra sản phẩm nào — kiểm tra mã SP."); return; }
      setRows((prev) => [...prev, ...add]);
      setQuickText("");
      setQuickMsg(`✓ Đã thêm ${add.length} món`);
    } catch {
      setQuickMsg("Lỗi phân tích");
    } finally {
      setQuickBusy(false);
    }
  };

  // Tự lấy giá theo khách khi chốt mã SP — chỉ điền khi giá đang trống (không đè giá tay)
  const autoPrice = async (i: number, code: string) => {
    if (!customerId || !code.trim()) return;
    const { price } = await loadListPrice(code);
    if (price) setRows((prev) => prev.map((r, idx) => (idx === i && !r.price ? { ...r, price } : r)));
  };

  const run = async (fn: () => Promise<void> | void) => {
    setBusy(true);
    try { await fn(); } catch (e: any) { toast(e?.message || "Lỗi", "err"); } finally { setBusy(false); }
  };
  const save = () => run(async () => {
    await onSave({ invoice: rows.filter((r) => (r.sp || "").trim()), discount: disc, pvc: p, vat: v });
    if (!createMode) setEditing(false);   // chi tiết: lưu xong về chế độ xem
  });
  const cancel = () => {
    setRows((invoice || []).map((it) => ({ sp: it.sp || "", sl: Number(it.sl ?? it.quantity ?? 0) || 0, price: Number(it.price) || 0, note: it.note || "" })));
    setDisc(Number(discount) || 0); setP(Number(pvc) || 0); setV(Number(vat) || 0);
    setEditing(false);
  };

  const priceTag = (sp: string, price: number) => {
    const info = listPrices[(sp || "").trim().toUpperCase()];
    if (!info || !info.price) return null;
    const name = info.list_name || "bảng giá";
    return Number(price) === info.price
      ? <span class="pricetag ok">✓ {name}</span>
      : <span class="pricetag">{name}: {money(info.price)}</span>;
  };

  // Nút liên quan hoá đơn KiotViet — gom chung ở đây (chưa có HĐ → Tạo; có HĐ → Xem/Xoá)
  const invActions = (
    <div class="inv-actions">
      {hasInvoice && invoiceCode ? (
        <div class="inv-created">✅ Đã tạo hoá đơn KiotViet · Mã <b>{invoiceCode}</b></div>
      ) : null}
      {hasInvoice ? (
        <div class="inv-btns">
          {onView ? <button class="btn small" onClick={onView}>👁️ Xem</button> : null}
          {onPrint ? <button class="btn small" disabled={busy} title="In HĐ + phiếu giao" onClick={() => run(onPrint)}>🖨️ In</button> : null}
          {canDelete && onDelete ? <button class="btn small danger" disabled={busy} onClick={() => run(onDelete)}>🗑️ Xoá</button> : null}
        </div>
      ) : (
        canCreate && onCreateInvoice ? (
          <button class="btn primary wide" disabled={busy} onClick={() => run(onCreateInvoice)}>🧾 Tạo HĐ KiotViet</button>
        ) : null
      )}
    </div>
  );

  // ── Chế độ XEM (mặc định ở trang chi tiết) ──────────────────────────────
  if (!editing) {
    return (
      <div class="card">
        <div class="row space">
          <b>Hoá đơn ({rows.length} món)</b>
          {hasInvoice
            ? <button class="lock-chip" onClick={() => toast("🔒 Đơn đã tạo hoá đơn KiotViet nên không sửa sản phẩm được nữa. Muốn sửa phải xoá HĐ trước.", "info")}>🔒 Đã chốt</button>
            : <button class="btn small" onClick={() => setEditing(true)}>✏️ Sửa</button>}
        </div>
        {rows.length === 0 ? (
          <p class="muted small">Chưa có sản phẩm. Bấm ✏️ Sửa để thêm.</p>
        ) : (
          <InvoiceTable items={rows} discount={disc} pvc={p} vat={v} debt={debt} />
        )}
        {customerId ? (
          <div class="inv-debt-ctl">
            <span class="muted small">Nợ trước (KiotViet){debt != null ? <>: <b>{money(debt)}đ</b></> : <span class="muted"> — chưa có</span>}</span>
            {debtLocked
              ? <button class="lock-chip" onClick={() => toast("🔒 Nợ đã chốt tại thời điểm tạo hoá đơn KiotViet — không kéo nợ mới được. Xoá HĐ nếu cần cập nhật lại.", "info")}>🔒 đã chốt</button>
              : (onRefreshDebt ? <button class="btn small" title="Kéo nợ KiotViet mới nhất" onClick={onRefreshDebt}>🔄 Cập nhật nợ</button> : null)}
          </div>
        ) : null}
        {invActions}
      </div>
    );
  }

  // ── Chế độ SỬA — mỗi món là 1 khối, canh gọn trên mobile ────────────────
  return (
    <div class="card">
      <div class="row space">
        <b>{createMode ? "Sản phẩm" : "Sửa hoá đơn"} ({rows.length} món)</b>
      </div>
      <div class="inv-edit">
        {rows.map((it, i) => (
          <div class="edit-row" key={i}>
            <div class="edit-top">
              <ProductInput value={it.sp} onChange={(c) => setRow(i, "sp", c)} onCommit={(c) => autoPrice(i, c)} />
              <button class="btn small danger" onClick={() => removeRow(i)}>✕</button>
            </div>
            <div class="edit-mid">
              <label class="fld sl">SL<input inputMode="numeric" value={it.sl} onInput={(e: any) => setRow(i, "sl", parseMoney(e.target.value))} /></label>
              <span class="times">×</span>
              <label class="fld price">Giá<input inputMode="numeric" value={it.price} onInput={(e: any) => setRow(i, "price", parseMoney(e.target.value))} /></label>
              <span class="eq">= <b>{money((it.price || 0) * (it.sl || 0))}đ</b></span>
            </div>
            <div class="edit-bot">
              {priceTag(it.sp, it.price)}
              <input class="note-inp" placeholder="ghi chú" value={it.note || ""} onInput={(e: any) => setRow(i, "note", e.target.value)} />
            </div>
          </div>
        ))}
      </div>
      <button class="btn wide" onClick={addRow}>+ Thêm dòng</button>

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
                      {money(it.price)}đ
                      {it.list_price != null && it.list_price > 0 && it.list_price !== it.price && (
                        <div class="old-price">{money(it.list_price)}đ</div>
                      )}
                    </td>
                    <td class="num"><b>{money(it.sub)}đ</b></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td colSpan={3}>Tổng thêm</td><td class="num"><b class="money">{money(quickPreview.total)}đ</b></td></tr>
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
        <div class="row">
          <button class="btn small" disabled={quickBusy || !quickText.trim()} onClick={quickAdd}>
            {quickBusy ? "Đang thêm…" : "⚡ Thêm nhanh"}
          </button>
          {quickMsg && <span class="muted small">{quickMsg}</span>}
        </div>
        <div class="muted small hint">
          💡 <code>&lt;mã SP&gt; &lt;SL&gt;</code> (mã trước, SL sau) · <code>5t</code>=5 thùng, <code>3b</code>=3 bịch, đổi số/đơn vị bằng <code>5t 60</code>/<code>3b 12</code>.
          {" "}Mặc định số/thùng: 50 (DM50 100; KDXDB/KGL/KMT/KMD/KHDX 5; KDDT 12) · số/bịch: 10 (KDDT 3) · DM180 1 lốc 12.
          {" "}Giá: nhập số sau SL để ghi đè (<code>K2L 10 25000</code>).
        </div>
      </div>

      <div class="adj">
        <label>Tiền hàng<b class="num">{money(tienHang)}đ</b></label>
        <label>Chiết khấu<input class="narrow" inputMode="numeric" value={disc} onInput={(e: any) => setDisc(parseMoney(e.target.value))} /></label>
        <label>PVC (ship)<input class="narrow" inputMode="numeric" value={p} onInput={(e: any) => setP(parseMoney(e.target.value))} /></label>
        <label>VAT
          <span class="row">
            <input class="narrow" inputMode="numeric" value={v} onInput={(e: any) => setV(parseMoney(e.target.value))} />
            <button class="btn small" onClick={() => setV(Math.round(tienHang * 0.08))}>8%</button>
          </span>
        </label>
        <div class="row space total"><b>Tổng thanh toán</b><b class="money">{money(tong)}đ</b></div>
      </div>

      <div class="row">
        <button class="btn primary" disabled={busy} onClick={save}>{busy ? "Đang lưu…" : createMode ? "💾 Lưu & tạo đơn" : "💾 Lưu"}</button>
        {!createMode && <button class="btn" disabled={busy} onClick={cancel}>Huỷ</button>}
      </div>
    </div>
  );
}
