// Trang HĐ ĐIỆN TỬ VNPT (NHÁP) của 1 đơn — #/order/:id/vnpt. Độc lập hoàn toàn
// với HĐ KiotViet: tên/giá/ĐVT từng dòng sửa tự do, 1 mức thuế chung, giá CHƯA
// gồm VAT. Mở lần đầu tự điền từ CACHE THEO KHÁCH (vnpt_profile — server trộn
// với dòng hàng của đơn); Lưu = đẩy nháp lên VNPT (chưa phát hành) + cập nhật
// cache khách. Server: server_app/vnpt_invoice_routes.py.
// Dòng CHIẾT KHẤU (kind "chiet_khau"): chỉ tên + số tiền, TRỪ vào tiền hàng
// trước thuế — lên VNPT thành dòng IsSum=2, SL 1 × đơn giá = số tiền. 2 kiểu:
// SỐ TIỀN gõ thẳng, hoặc % (pct) = % của tổng CÁC DÒNG HÀNG — tiền + tên tự
// sinh ("Chiết khấu thương mại 5%, số tiền 1.401.250 đồng"), server tính lại
// (server_app/vnpt_invoice_domain.apply_discount_pct) nên số cuối luôn theo server.
import { useEffect, useState } from "preact/hooks";
import { getJSON, getVnptInvoice, saveVnptInvoice, vnptInvoicePdfUrl, vnptInvoicePngUrl, type VnptBuyer, type VnptLine } from "../api";
import { SingleImageViewer } from "../detail/SingleImageViewer";
import { downloadFileFromUrl } from "../downloadFile";
import { money, parseMoney, parseQty, fmtQty } from "../format";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { ErrorState, Loading } from "../ui/states";

const VAT_OPTS: Array<[number, string]> = [[-1, "KCT"], [0, "0%"], [5, "5%"], [8, "8%"], [10, "10%"]];
type Row = VnptLine & { slText?: string; pctText?: string };

const fmtPct = (p: number) => (Number.isInteger(p) ? String(p) : String(p).replace(".", ",")) + "%";
/** Cùng công thức với server (discount_name) để preview khớp chữ in. */
const discountName = (pct: number, amount: number) => `Chiết khấu thương mại ${fmtPct(pct)}, số tiền ${money(amount)} đồng`;
const parsePct = (raw: string) => { const v = parseFloat(raw.replace(",", ".")); return Number.isFinite(v) && v > 0 ? Math.min(v, 100) : 0; };

export function OrderVnptInvoice({ threadId }: { threadId: string }) {
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState<any>(null);
  const [buyer, setBuyer] = useState<VnptBuyer>({ cus_name: "" });
  const [rows, setRows] = useState<Row[]>([]);
  const [vatRate, setVatRate] = useState(8);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState(false);   // xem PNG bản thể hiện trong app
  const [mstBusy, setMstBusy] = useState(false);

  // Tra MST trên dữ liệu Cục Thuế (server proxy VietQR) → tự điền tên + địa chỉ
  const lookupMst = async () => {
    const mst = (buyer.tax_code || "").replace(/\s/g, "");
    if (!mst) return;
    setMstBusy(true);
    try {
      const j = await getJSON(`/api/mst-lookup?mst=${encodeURIComponent(mst)}`, { cache: false });
      if (!j.found) { toast("Không tìm thấy MST này trên dữ liệu Cục Thuế", "err"); return; }
      setBuyer((p) => ({ ...p, tax_code: mst, cus_name: j.name || p.cus_name, address: j.address || p.address }));
      toast(j.active ? `✓ ${j.status}` : `⚠ ${j.status || "Không rõ trạng thái"}`, j.active ? "ok" : "err");
    } catch (e: any) {
      toast(e?.message || "Lỗi tra MST", "err");
    } finally { setMstBusy(false); }
  };

  const load = () => {
    setErr("");
    getVnptInvoice(threadId)
      .then((j) => {
        setLoaded(j);
        const src = j.draft || j.prefill || {};
        setBuyer({ payment_method: "TM/CK", ...(src.buyer || {}) });
        setRows((src.lines || []).map((l: any) => ({ ...l, qty: Number(l.qty) || 1, price: Number(l.price) || 0 })));
        setVatRate(typeof src.vat_rate === "number" ? src.vat_rate : 8);
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, [threadId]);

  if (err && !loaded) return <ErrorState msg={err} onRetry={load} />;
  if (!loaded) return <Loading />;

  const setB = (k: keyof VnptBuyer, v: string) => setBuyer((p) => ({ ...p, [k]: v }));
  const setRow = (i: number, f: string, v: any) => setRows((p) => p.map((r, idx) => (idx === i ? { ...r, [f]: v } : r)));
  const removeRow = (i: number) => setRows((p) => p.filter((_, idx) => idx !== i));
  const addRow = () => setRows((p) => [...p, { name: "", unit: "", qty: 1, price: 0 }]);
  const addDiscountRow = () => setRows((p) => [...p, { name: "Chiết khấu thương mại", unit: "", qty: 1, price: 0, kind: "chiet_khau" }]);
  const selectAll = (e: any) => (e.currentTarget as HTMLInputElement).select();

  const isCK = (r: Row) => r.kind === "chiet_khau";
  const goods = rows.filter((r) => !isCK(r)).reduce((s, r) => s + Math.round((r.qty || 0) * (r.price || 0)), 0);
  // CK theo %: tiền = % × tổng dòng hàng (làm tròn lên .5 như server), tên tự sinh
  const ckAmount = (r: Row) => (r.pct ? Math.floor((goods * r.pct) / 100 + 0.5) : Math.round(r.price || 0));
  const discount = rows.filter(isCK).reduce((s, r) => s + ckAmount(r), 0);
  const total = goods - discount;
  const vatAmount = vatRate < 0 ? 0 : Math.round((total * vatRate) / 100);
  const grand = total + vatAmount;

  const save = async () => {
    if (busy) return;
    if (loaded?.draft?.published) { toast("Hoá đơn đã PHÁT HÀNH — không sửa được nữa", "err"); return; }
    // chặn sớm 3 trường bắt buộc cho đỡ 1 vòng server (server vẫn validate + checksum MST)
    if (!(buyer.cus_name || "").trim()) { toast("Thiếu tên đơn vị (bắt buộc)", "err"); return; }
    if (!(buyer.tax_code || "").trim()) { toast("Thiếu mã số thuế (bắt buộc)", "err"); return; }
    if (!(buyer.address || "").trim()) { toast("Thiếu địa chỉ (bắt buộc)", "err"); return; }
    if (total < 0) { toast("Chiết khấu vượt quá tiền hàng", "err"); return; }
    setBusy(true);
    try {
      const lines = rows
        .filter((r) => (r.name || "").trim() || (isCK(r) && r.pct))
        .map(({ slText, pctText, ...r }) => (isCK(r) && r.pct
          ? { ...r, price: ckAmount(r), name: discountName(r.pct, ckAmount(r)) }
          : { ...r, pct: undefined, name: r.name.trim() }));
      const j = await saveVnptInvoice(threadId, { buyer, lines, vat_rate: vatRate });
      toast(loaded.draft ? "Đã cập nhật nháp trên VNPT" : "Đã tạo nháp trên VNPT", "ok");
      if (j.warn) toast(j.warn, "err");
      window.location.hash = `#/order/${threadId}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu nháp", "err");
    } finally {
      setBusy(false);
    }
  };

  // required: MST + tên đơn vị + địa chỉ BẮT BUỘC (Duy chốt 2026-08-26) — server cùng rule
  const fld = (label: string, k: keyof VnptBuyer, ph = "", required = false) => (
    <div class="mt-1">
      <div class="page-head-sub">{label}{required && <span class="t-danger"> *</span>}</div>
      <input class="note-inp" style="width:100%" placeholder={ph} value={(buyer[k] as string) || ""}
        onInput={(e: any) => setB(k, e.target.value)} />
    </div>
  );

  return (
    <div class="prod-detail">
      <PageHead fallback={`#/order/${threadId}`}
        title={loaded.draft ? "Sửa HĐ điện tử nháp" : "Tạo HĐ điện tử nháp"}
        sub={`VNPT · ${loaded.pattern} · ${loaded.serial} — chưa phát hành`}
        right={loaded.draft ? (
          <span class="row">
            <button class="btn small" onClick={() => setViewing(true)}>
              <Icon name="eye" size={14} /> Xem
            </button>
            <button class="btn small" onClick={() => downloadFileFromUrl(vnptInvoicePdfUrl(threadId), `HD-nhap-${threadId}.pdf`)}>
              <Icon name="download" size={14} /> PDF
            </button>
          </span>
        ) : undefined} />
      {viewing && (
        <SingleImageViewer src={vnptInvoicePngUrl(threadId)} title="hoá đơn nháp"
          onClose={() => setViewing(false)} />
      )}
      {!loaded.configured && (
        <div class="card"><span class="t-danger">Server chưa cấu hình VNPT_INV_* trong .env — lưu sẽ lỗi.</span></div>
      )}
      {loaded.draft?.published && (
        <div class="card"><b class="t-ok">✅ Hoá đơn ĐÃ PHÁT HÀNH trên VNPT
          {loaded.draft.invoice_no ? ` · Số ${String(loaded.draft.invoice_no).padStart(8, "0")}` : ""}</b>
          <div class="muted small">Không sửa/xoá được nữa — cần điều chỉnh thì xử lý trên trang VNPT.</div></div>
      )}

      <section class="card">
        <div class="ie-head">Người mua</div>
        {/* MST đặt TRÊN cùng: gõ MST → 「Tra」 (tra cứu công khai từ dữ liệu Cục
            Thuế qua /api/mst-lookup) tự điền tên đơn vị + địa chỉ bên dưới */}
        <div class="mt-1">
          <div class="page-head-sub">Mã số thuế / số định danh<span class="t-danger"> *</span></div>
          <div class="row">
            <input class="note-inp" style="flex:1;min-width:0" placeholder="MST 10 số hoặc CCCD 12 số"
              value={buyer.tax_code || ""} onInput={(e: any) => setB("tax_code", e.target.value)} />
            <button class="btn small" disabled={mstBusy || !(buyer.tax_code || "").trim()} onClick={lookupMst}>
              {mstBusy ? "…" : <><Icon name="search" size={14} /> Tra</>}
            </button>
          </div>
        </div>
        {fld("Tên đơn vị (in trên HĐ)", "cus_name", "Công ty TNHH …", true)}
        {fld("Địa chỉ", "address", "", true)}
        {fld("Người mua hàng", "buyer_name")}
        {fld("Điện thoại", "phone")}
        {fld("Email nhận hoá đơn", "email", "vd: ketoan@congty.vn (nhiều mail cách nhau ;)")}
        <div class="mt-1">
          <div class="page-head-sub">Hình thức thanh toán</div>
          <div class="chips">
            {["TM/CK", "TM", "CK"].map((m) => (
              <button key={m} class={"chip" + ((buyer.payment_method || "TM/CK") === m ? " active" : "")}
                onClick={() => setB("payment_method", m)}>{m}</button>
            ))}
          </div>
        </div>
      </section>

      <section class="card">
        <div class="ie-head">Hàng hoá <span class="ie-count">{rows.length} dòng</span></div>
        <div class="inv-edit">
          {rows.map((r, i) => isCK(r) ? (
            /* Dòng CHIẾT KHẤU: 2 kiểu — SỐ TIỀN gõ thẳng, hoặc % của tổng dòng hàng
               (tiền + tên tự sinh, không sửa tên) — hiện âm để thấy ngay là trừ */
            <div class="edit-row vnpt-ck" key={i}>
              <div class="er-main">
                <span class="chip active small" title="Dòng chiết khấu — trừ vào tiền hàng">CK</span>
                {r.pct ? (
                  <span class="note-inp muted" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                    title="Tên tự sinh theo %">{discountName(r.pct, ckAmount(r))}</span>
                ) : (
                  <input class="note-inp" style="flex:1;min-width:0" placeholder="Nội dung chiết khấu in trên HĐ"
                    value={r.name} onInput={(e: any) => setRow(i, "name", e.target.value)} />
                )}
                <button class="er-del" title="Xoá dòng" onClick={() => removeRow(i)}><Icon name="close" size={15} /></button>
              </div>
              <div class="er-sub">
                <span class="seg small">
                  <button class={"seg-btn" + (!r.pct ? " active" : "")} title="Gõ thẳng số tiền chiết khấu"
                    onClick={() => setRows((p) => p.map((x, idx) => (idx === i ? { ...x, pct: undefined, pctText: undefined, price: ckAmount(x) } : x)))}>Số tiền</button>
                  <button class={"seg-btn" + (r.pct ? " active" : "")} title="% của tổng các dòng hàng"
                    onClick={() => setRows((p) => p.map((x, idx) => (idx === i ? { ...x, pct: x.pct || 5, pctText: undefined } : x)))}>%</button>
                </span>
                {r.pct ? (
                  <>
                    <input class="er-sl" inputMode="decimal" placeholder="%" title="% chiết khấu trên tổng dòng hàng"
                      value={r.pctText ?? (r.pct ? String(r.pct).replace(".", ",") : "")} onFocus={selectAll}
                      onInput={(e: any) => {
                        const raw = e.target.value;
                        setRows((p) => p.map((x, idx) => (idx === i ? { ...x, pctText: raw, pct: parsePct(raw) || x.pct } : x)));
                      }}
                      onBlur={() => setRows((p) => p.map((x, idx) => (idx === i ? { ...x, pctText: undefined } : x)))} />
                    <span class="muted small">% × {money(goods)}</span>
                  </>
                ) : (
                  <input class="er-price" inputMode="numeric" placeholder="số tiền" title="Số tiền chiết khấu (chưa thuế)"
                    value={r.price ? money(r.price) : ""} onFocus={selectAll}
                    onInput={(e: any) => setRow(i, "price", parseMoney(e.target.value))} />
                )}
                <span class="eq">= <b class="num t-danger">−{money(ckAmount(r))}</b></span>
              </div>
            </div>
          ) : (
            <div class="edit-row" key={i}>
              <div class="er-main">
                <input class="note-inp" style="flex:1;min-width:0" placeholder="Tên hàng in trên HĐ"
                  value={r.name} onInput={(e: any) => setRow(i, "name", e.target.value)} />
                <button class="er-del" title="Xoá dòng" onClick={() => removeRow(i)}><Icon name="close" size={15} /></button>
              </div>
              <div class="er-sub">
                <input class="er-sl" placeholder="ĐVT" title="Đơn vị tính" value={r.unit || ""}
                  onFocus={selectAll} onInput={(e: any) => setRow(i, "unit", e.target.value)} />
                <input class="er-sl" inputMode="decimal" placeholder="SL" title="Số lượng"
                  value={r.slText ?? (r.qty ? fmtQty(r.qty) : "")} onFocus={selectAll}
                  onInput={(e: any) => {
                    const raw = e.target.value;
                    setRows((p) => p.map((x, idx) => (idx === i ? { ...x, slText: raw, qty: parseQty(raw) } : x)));
                  }}
                  onBlur={() => setRows((p) => p.map((x, idx) => (idx === i ? { ...x, slText: undefined } : x)))} />
                <span class="times">×</span>
                <input class="er-price" inputMode="numeric" placeholder="đơn giá" title="Đơn giá CHƯA gồm VAT"
                  value={r.price ? money(r.price) : ""} onFocus={selectAll}
                  onInput={(e: any) => setRow(i, "price", parseMoney(e.target.value))} />
                <span class="eq">= <b class="num">{money(Math.round((r.qty || 0) * (r.price || 0)))}</b></span>
              </div>
            </div>
          ))}
        </div>
        <div class="row">
          <button class="er-add" style="flex:1;width:auto" onClick={addRow}><Icon name="plus" size={15} /> Thêm dòng</button>
          <button class="er-add" style="flex:1;width:auto" onClick={addDiscountRow} title="Thêm dòng chiết khấu (trừ vào tiền hàng trước thuế)">
            <Icon name="minus" size={15} /> Thêm chiết khấu
          </button>
        </div>

        <div class="ie-sum">
          <div class="sum-row"><span>Thuế GTGT</span>
            <span class="chips">
              {VAT_OPTS.map(([v, t]) => (
                <button key={v} class={"chip" + (vatRate === v ? " active" : "")} onClick={() => setVatRate(v)}>{t}</button>
              ))}
            </span>
          </div>
          {discount > 0 && (
            <>
              <div class="sum-row"><span>Tiền hàng</span><b class="num">{money(goods)}</b></div>
              <div class="sum-row"><span>Chiết khấu</span><b class="num t-danger">−{money(discount)}</b></div>
            </>
          )}
          <div class="sum-row"><span>Cộng tiền hàng (chưa thuế)</span><b class={"num" + (total < 0 ? " t-danger" : "")}>{money(total)}</b></div>
          <div class="sum-row"><span>Tiền thuế {vatRate < 0 ? "(KCT)" : `${vatRate}%`}</span><b class="num">{money(vatAmount)}</b></div>
          <div class="sum-total"><span>Tổng thanh toán</span><b class="num">{money(grand)}</b></div>
        </div>

        <div class="ie-actions">
          <button class="btn primary" disabled={busy || !!loaded.draft?.published} onClick={save}>
            {busy ? "Đang lưu…" : loaded.draft?.published ? "Đã phát hành — khoá sửa"
              : <><Icon name="save" size={16} /> {loaded.draft ? "Cập nhật nháp VNPT" : "Tạo nháp VNPT"} · {money(grand)}</>}
          </button>
          <button class="btn" disabled={busy} onClick={() => (window.location.hash = `#/order/${threadId}`)}>Huỷ</button>
        </div>
        {loaded.draft?.fkey && <div class="page-head-sub mt-1">fkey: {loaded.draft.fkey}</div>}
      </section>
    </div>
  );
}
