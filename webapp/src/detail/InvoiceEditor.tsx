// Trình NHẬP hoá đơn — thuần chỉnh sửa, dùng cho trang Sửa hoá đơn
// (OrderInvoiceEdit) và tab Nâng cao trang tạo đơn (CreateOrder, createMode).
// Dòng SP có autocomplete + tự lấy giá theo khách (/api/customer/price),
// điều chỉnh Chiết khấu/PVC/VAT, tổng sống. (Nhập nhanh bằng text đã có ở tab
// Nhanh của trang cha — không lặp lại ở đây.)
// KHÔNG còn chế độ xem / nút HĐ KiotViet — phần đó nằm ở khối Hoá đơn của
// OrderDetail. Parent quyết định onSave làm gì và điều hướng sau khi lưu.
import { useEffect, useRef, useState } from "preact/hooks";
import { fetchCustomerPrice, searchProducts, type PriceInfo } from "../api";
import { money, parseMoney, parseQty, fmtQty } from "../format";
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

export function InvoiceEditor({ customerId, invoice, discount, pvc, vat, onSave, onCancel, createMode, priceOnly }: {
  customerId?: string;
  invoice: any[];
  discount?: number; pvc?: number; vat?: number;
  onSave: (payload: EditorPayload) => Promise<void> | void;
  onCancel?: () => void;   // trang sửa: Huỷ → quay về chi tiết; createMode không cần
  createMode?: boolean;    // form tạo đơn → nhãn nút "Lưu & tạo đơn"
  priceOnly?: boolean;     // đơn đã chốt kho: khoá mã hàng + SL (không thêm/xoá dòng); giá/ghi chú/CK/PVC/VAT vẫn sửa
}) {
  // slText = chuỗi user đang gõ cho ô SL (giữ dấu ',' đang gõ dở như "1,"); sl = số
  // đã parse (float) dùng để tính. Không giữ raw thì input controlled sẽ nuốt dấu phẩy.
  const [rows, setRows] = useState<Array<EditorRow & { slText?: string }>>([]);
  const [disc, setDisc] = useState(0);
  const [p, setP] = useState(0);
  const [v, setV] = useState(0);
  const [vat8Enabled, setVat8Enabled] = useState(false);
  const [busy, setBusy] = useState(false);

  // Giá + bảng giá theo mã SP (đã hoa) — để ghi rõ giá lấy từ bảng giá nào.
  // Cache theo MÃ, không theo khách → đổi khách phải xoá cache (effect dưới).
  const [listPrices, setListPrices] = useState<Record<string, PriceInfo>>({});
  const listRef = useRef<Record<string, PriceInfo>>({});
  const custRef = useRef(customerId);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  // Tra 1 lần giá bảng cho 1 mã (cache trong listRef); trả PriceInfo
  const loadListPrice = async (code: string): Promise<PriceInfo> => {
    const key = (code || "").trim().toUpperCase();
    const empty: PriceInfo = { price: 0, source: null, list_name: null };
    if (!key || !customerId) return empty;
    if (key in listRef.current) return listRef.current[key];
    const info = await fetchCustomerPrice(customerId, key).catch(() => empty);
    if (custRef.current !== customerId) return info;   // khách đã đổi khi đang tra — bỏ, khỏi cache giá khách cũ
    listRef.current = { ...listRef.current, [key]: info };
    setListPrices(listRef.current);
    return info;
  };

  // Đổi khách giữa chừng (bước 1 trang sửa hoá đơn) → giá bảng đã tra là của
  // khách CŨ: xoá cache + tra lại theo khách mới cho các mã đang có trên form.
  // Dòng SP + giá đã nhập GIỮ NGUYÊN (giá là snapshot) — chỉ chú thích bảng giá
  // và nút đặt-lại-giá cập nhật theo khách mới.
  useEffect(() => {
    if (custRef.current === customerId) return;
    custRef.current = customerId;
    listRef.current = {};
    setListPrices({});
    const codes = [...new Set(rowsRef.current.map((r) => (r.sp || "").trim().toUpperCase()).filter(Boolean))];
    codes.forEach((c) => { loadListPrice(c); });
  }, [customerId]);

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
  // Tự bật chế độ 8% khi đơn nạp vào có VAT = 8% tiền hàng (VAT phần trăm, không phải
  // số cố định) → sửa SL/giá thì VAT tự tính lại. Chỉ xét 1 LẦN lúc seed (guard ref)
  // nên không đè khi user tự chỉnh VAT hoặc tắt 8% sau đó.
  const vat8Seeded = useRef(false);
  useEffect(() => {
    if (vat8Seeded.current || !invoice || invoice.length === 0) return;
    vat8Seeded.current = true;
    const sv = Number(vat) || 0;
    const goods = invoice.reduce((s: number, it: any) => s + (Number(it.price) || 0) * (Number(it.sl ?? it.quantity) || 0), 0);
    if (sv > 0 && goods > 0 && Math.abs(sv - Math.round(goods * 0.08)) <= 1) setVat8Enabled(true);
  }, [invoice, vat]);

  const tienHang = rows.reduce((s, r) => s + (r.price || 0) * (r.sl || 0), 0);
  // Tính trực tiếp thay vì đồng bộ bằng effect: tắt VAT có hiệu lực ngay và
  // không thể bị một effect chạy trễ ghi đè lại. (Chốt kho chỉ khoá mã hàng +
  // SL — VAT/giá/ghi chú/CK/PVC vẫn sửa được, server cùng rule.)
  const currentVat = vat8Enabled ? Math.round(tienHang * 0.08) : v;
  const tong = tienHang - disc + p + currentVat;

  const toggleVat8 = () => {
    const enabled = !vat8Enabled;
    setVat8Enabled(enabled);
    if (!enabled) setV(0);
  };
  const selectAll = (e: any) => (e.currentTarget as HTMLInputElement).select();

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
    try { await onSave({ invoice: rows.filter((r) => (r.sp || "").trim()).map(({ slText, ...r }) => r), discount: disc, pvc: p, vat: currentVat }); }
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

  // ── Chỉnh sửa — kiểu PHIẾU TÍNH TIỀN: vạch mảnh, số tabular có chấm nghìn ──
  return (
    <div class="card">
      <div class="ie-head">Sản phẩm <span class="ie-count">{rows.length} món</span></div>
      <div class="inv-edit">
        {rows.map((it, i) => (
          <div class="edit-row" key={i}>
            <div class="er-main">
              {priceOnly
                ? <span class="er-product-fixed">{it.sp}</span>
                : <ProductInput value={it.sp} onChange={(c) => setRow(i, "sp", c)} onCommit={(c) => autoPrice(i, c)} />}
              <input class="er-sl" inputMode="decimal" title="Số lượng (nhập được số lẻ, vd 1,5)" placeholder="SL"
                value={it.slText ?? (it.sl ? fmtQty(it.sl) : "")}
                disabled={priceOnly} onFocus={selectAll}
                onInput={(e: any) => {
                  const raw = e.target.value;
                  setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, slText: raw, sl: parseQty(raw) } : r)));
                }}
                onBlur={() => setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, slText: undefined } : r)))} />
              <span class="times">×</span>
              <input class="er-price" inputMode="numeric" title="Đơn giá" placeholder="giá" value={it.price ? money(it.price) : ""}
                onFocus={selectAll} onInput={(e: any) => setRow(i, "price", parseMoney(e.target.value))} />
              {(() => {
                const info = listPrices[(it.sp || "").trim().toUpperCase()];
                return info && info.price && Number(it.price) !== info.price ? (
                  <button type="button" class="price-reset" title={`Đặt lại giá bảng: ${money(info.price)}`}
                    onClick={() => setRow(i, "price", info.price)}>
                    <Icon name="refresh" size={14} />
                  </button>
                ) : null;
              })()}
              {!priceOnly && <button class="er-del" title="Xoá dòng" onClick={() => removeRow(i)}><Icon name="close" size={15} /></button>}
            </div>
            <div class="er-sub">
              {priceTag(it.sp, it.price)}
              <input class="note-inp" placeholder="ghi chú…" value={it.note || ""}
                onFocus={selectAll} onInput={(e: any) => setRow(i, "note", e.target.value)} />
              <span class="eq">= <b class="num">{money((it.price || 0) * (it.sl || 0))}</b></span>
            </div>
          </div>
        ))}
      </div>
      {!priceOnly && <button class="er-add" onClick={addRow}><Icon name="plus" size={15} /> Thêm dòng</button>}

      <div class="ie-sum">
        <div class="sum-row"><span>Tiền hàng</span><b class="num">{money(tienHang)}</b></div>
        <div class="sum-row"><span>Chiết khấu</span><input class="sum-inp" inputMode="numeric" placeholder="0" value={disc ? money(disc) : ""}
          onFocus={selectAll} onInput={(e: any) => setDisc(parseMoney(e.target.value))} /></div>
        <div class="sum-row"><span>PVC (ship)</span><input class="sum-inp" inputMode="numeric" placeholder="0" value={p ? money(p) : ""}
          onFocus={selectAll} onInput={(e: any) => setP(parseMoney(e.target.value))} /></div>
        <div class="sum-row"><span>VAT</span>
          <span class="sum-vat">
            <button type="button" class={vat8Enabled ? "chip8 on" : "chip8"}
              aria-pressed={vat8Enabled} title={vat8Enabled ? "Tắt VAT 8%" : "Bật VAT 8%"}
              onClick={toggleVat8}>8%</button>
            <input class="sum-inp" inputMode="numeric" placeholder="0" value={currentVat ? money(currentVat) : ""}
              onFocus={selectAll} onInput={(e: any) => { setVat8Enabled(false); setV(parseMoney(e.target.value)); }} />
          </span>
        </div>
        <div class="sum-total"><span>Tổng thanh toán</span><b class="num">{money(tong)}</b></div>
      </div>

      <div class="ie-actions">
        <button class="btn primary" disabled={busy} onClick={save}>
          {busy ? "Đang lưu…" : <><Icon name="save" size={16} /> {createMode ? "Lưu & tạo đơn" : "Lưu"} · {money(tong)}</>}
        </button>
        {onCancel && <button class="btn" disabled={busy} onClick={onCancel}>Huỷ</button>}
      </div>
    </div>
  );
}
