// Trang HĐ ĐIỆN TỬ VNPT (NHÁP) của 1 đơn — #/order/:id/vnpt. Độc lập hoàn toàn
// với HĐ KiotViet: tên/giá/ĐVT từng dòng sửa tự do, 1 mức thuế chung, giá CHƯA
// gồm VAT. Mở lần đầu tự điền từ CACHE THEO KHÁCH (vnpt_profile — server trộn
// với dòng hàng của đơn); Lưu = đẩy nháp lên VNPT (chưa phát hành) + cập nhật
// cache khách. Server: server_app/vnpt_invoice_routes.py.
import { useEffect, useState } from "preact/hooks";
import { getVnptInvoice, saveVnptInvoice, vnptInvoicePdfUrl, type VnptBuyer, type VnptLine } from "../api";
import { money, parseMoney, parseQty, fmtQty } from "../format";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { ErrorState, Loading } from "../ui/states";

const VAT_OPTS: Array<[number, string]> = [[-1, "KCT"], [0, "0%"], [5, "5%"], [8, "8%"], [10, "10%"]];
type Row = VnptLine & { slText?: string };

export function OrderVnptInvoice({ threadId }: { threadId: string }) {
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState<any>(null);
  const [buyer, setBuyer] = useState<VnptBuyer>({ cus_name: "" });
  const [rows, setRows] = useState<Row[]>([]);
  const [vatRate, setVatRate] = useState(8);
  const [busy, setBusy] = useState(false);

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
  const selectAll = (e: any) => (e.currentTarget as HTMLInputElement).select();

  const total = rows.reduce((s, r) => s + Math.round((r.qty || 0) * (r.price || 0)), 0);
  const vatAmount = vatRate < 0 ? 0 : Math.round((total * vatRate) / 100);
  const grand = total + vatAmount;

  const save = async () => {
    if (busy) return;
    // chặn sớm 3 trường bắt buộc cho đỡ 1 vòng server (server vẫn validate + checksum MST)
    if (!(buyer.cus_name || "").trim()) { toast("Thiếu tên đơn vị (bắt buộc)", "err"); return; }
    if (!(buyer.tax_code || "").trim()) { toast("Thiếu mã số thuế (bắt buộc)", "err"); return; }
    if (!(buyer.address || "").trim()) { toast("Thiếu địa chỉ (bắt buộc)", "err"); return; }
    setBusy(true);
    try {
      const lines = rows
        .filter((r) => (r.name || "").trim())
        .map(({ slText, ...r }) => ({ ...r, name: r.name.trim() }));
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
          <button class="btn small" onClick={() => window.open(vnptInvoicePdfUrl(threadId), "_blank")}>
            <Icon name="download" size={14} /> PDF
          </button>
        ) : undefined} />
      {!loaded.configured && (
        <div class="card"><span class="t-danger">Server chưa cấu hình VNPT_INV_* trong .env — lưu sẽ lỗi.</span></div>
      )}

      <section class="card">
        <div class="ie-head">Người mua</div>
        {fld("Tên đơn vị (in trên HĐ)", "cus_name", "Công ty TNHH …", true)}
        {fld("Mã số thuế", "tax_code", "10 số (hoặc 10 số-3 số)", true)}
        {fld("Địa chỉ", "address", "", true)}
        {fld("Người mua hàng", "buyer_name")}
        {fld("Điện thoại", "phone")}
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
          {rows.map((r, i) => (
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
        <button class="er-add" onClick={addRow}><Icon name="plus" size={15} /> Thêm dòng</button>

        <div class="ie-sum">
          <div class="sum-row"><span>Thuế GTGT</span>
            <span class="chips">
              {VAT_OPTS.map(([v, t]) => (
                <button key={v} class={"chip" + (vatRate === v ? " active" : "")} onClick={() => setVatRate(v)}>{t}</button>
              ))}
            </span>
          </div>
          <div class="sum-row"><span>Cộng tiền hàng (chưa thuế)</span><b class="num">{money(total)}</b></div>
          <div class="sum-row"><span>Tiền thuế {vatRate < 0 ? "(KCT)" : `${vatRate}%`}</span><b class="num">{money(vatAmount)}</b></div>
          <div class="sum-total"><span>Tổng thanh toán</span><b class="num">{money(grand)}</b></div>
        </div>

        <div class="ie-actions">
          <button class="btn primary" disabled={busy} onClick={save}>
            {busy ? "Đang lưu…" : <><Icon name="save" size={16} /> {loaded.draft ? "Cập nhật nháp VNPT" : "Tạo nháp VNPT"} · {money(grand)}</>}
          </button>
          <button class="btn" disabled={busy} onClick={() => (window.location.hash = `#/order/${threadId}`)}>Huỷ</button>
        </div>
        {loaded.draft?.fkey && <div class="page-head-sub mt-1">fkey: {loaded.draft.fkey}</div>}
      </section>
    </div>
  );
}
