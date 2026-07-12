// Trang "Sửa hoá đơn" của 1 đơn (#/order/:id/hoa-don) — 2 BƯỚC như tab Nâng cao
// trang tạo đơn, liên kết nhau: ① Khách hàng (nợ KiotViet + bảng giá + Đổi khách
// qua /api/order/assign-customer) → ② Sản phẩm & hoá đơn (InvoiceEditor lấy giá
// theo khách ở bước 1 — đổi khách là chú thích giá bảng/gợi ý giá cập nhật ngay).
// Lưu xong quay về chi tiết đơn. Mọi thao tác HĐ KiotViet (tạo/xem/in/xoá/kéo nợ)
// nằm ở khối Hoá đơn của OrderDetail. Đơn đã có HĐ KiotViet → khoá (phải xoá HĐ trước).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getJSON, postJSON, lockInvoiceEdit, unlockInvoiceEdit, previewOrder, refreshCustomerDebt, type OrderPreview } from "../api";
import { money, initial } from "../format";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";
import { PriceListModal } from "../detail/PriceListModal";
import { invalidateListCache } from "./OrdersList";
import { toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function OrderInvoiceEdit({ threadId }: { threadId: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");
  const [editHolder, setEditHolder] = useState<string | null>(null);   // NGƯỜI KHÁC đang sửa
  const [changingCust, setChangingCust] = useState(false);             // đang mở ô đổi khách
  const [cust, setCust] = useState<OrderPreview["customer"]>(null);    // nợ + bảng giá khách hiện tại
  const [plCust, setPlCust] = useState<string | null>(null);           // popup bảng giá

  const reload = async () => {
    try { setDetail(await getJSON(`/api/order/${threadId}`)); setErr(""); }
    catch (ex: any) { setErr(ex.message); }
  };
  useEffect(() => { reload(); }, [threadId]);

  const j = detail?.data || {};
  const custKey: string = j.khach_hang_id || j.khID || "";
  const custName: string = j.customer_name || "";
  const hasInvoice = !!j.kiotvietInvoiceID;
  const stockLocked = !!j.stock_confirmed;   // đã chốt xuất kho → khoá dù đã xoá HĐ
  const locked = hasInvoice || stockLocked;
  const editable = !!detail && !locked;      // chỉ giữ khoá khi đơn còn sửa được
  const canChange = editable && !editHolder; // đổi khách: server cũng cấm khi có HĐ KiotViet

  // Bước 1: kéo nợ + tên bảng giá của khách (cùng đường với tab Nâng cao trang
  // tạo đơn — previewOrder text rỗng trả customer đầy đủ, rồi kéo nợ KiotViet MỚI).
  useEffect(() => {
    if (!custKey) { setCust(null); return; }
    let alive = true;
    previewOrder("", custKey)
      .then((r) => { if (alive) setCust(r.customer); })
      .catch(() => {});
    return () => { alive = false; };
  }, [custKey]);
  useEffect(() => {
    const id = cust?.id;
    if (!id) return;
    let alive = true;
    refreshCustomerDebt(id)
      .then((c) => { if (alive) setCust((p) => (p && p.id === id ? { ...p, debt: c.debt } : p)); })
      .catch(() => {});
    return () => { alive = false; };
  }, [cust?.id]);

  // Giữ khoá "1 người sửa hoá đơn" khi trang mở: heartbeat 20s, nhả khi rời trang. Người khác
  // giữ (mine=false) → hiện banner + poll nhanh 4s để bắt lúc họ nhả rồi tự vào sửa.
  useEffect(() => {
    if (!editable) return;
    let alive = true; let t: any;
    const beat = async () => {
      let blocked = false;
      try {
        const r = await lockInvoiceEdit(threadId);
        blocked = !!(r && r.mine === false);
        if (alive) setEditHolder(blocked ? r.holder : null);
      } catch { /* im lặng — thử lại nhịp sau */ }
      if (alive) t = setTimeout(beat, blocked ? 4000 : 20000);
    };
    beat();
    return () => { alive = false; clearTimeout(t); unlockInvoiceEdit(threadId).catch(() => {}); };
  }, [editable, threadId]);

  // Đổi/gán khách cho đơn — lưu ngay (như khối Khách ở OrderDetail); custKey đổi
  // → InvoiceEditor tự tra lại giá bảng theo khách mới, dòng SP đang sửa GIỮ NGUYÊN.
  const assignCustomer = async (c: { key: string; name: string } | null) => {
    if (!c) return;
    try {
      await postJSON("/api/order/assign-customer", { thread_id: Number(threadId), customer_key: c.key });
      setChangingCust(false);
      setDetail((p: any) => (p ? { ...p, data: { ...p.data, khach_hang_id: c.key, customer_name: c.name } } : p));
      invalidateListCache();
      toast(`✅ Đã gán khách: ${c.name}`, "ok");
    } catch (ex: any) { toast(`❌ ${ex.message}`, "err"); }
  };

  // Thay entry "Sửa hoá đơn" bằng trang chi tiết. Nếu chỉ gán location.hash,
  // trình duyệt sẽ thêm một entry mới và nút Back sẽ mở lại form vừa rời.
  const goBack = () => { window.location.replace(`#/order/${threadId}`); };
  const saveInvoice = async (payload: EditorPayload) => {
    await postJSON("/api/order/invoice/update", { thread_id: Number(threadId), ...payload });
    invalidateListCache();
    toast("✅ Đã lưu hoá đơn", "ok");
    goBack();
  };

  if (err) return <ErrorState msg={err} onRetry={reload} />;
  if (!detail) return <Loading />;

  return (
    <div class="co-adv">
      <div class="prod-detail-head">
        <BackLink fallback={`#/order/${threadId}`} />
        <div><div class="prod-sp big">Sửa hoá đơn · đơn #{threadId}</div></div>
      </div>
      <div class="card">
        <div class="ie-head">Nội dung đơn hàng</div>
        <pre class="order-text">{j.text || j.text_raw || "(trống)"}</pre>
      </div>

      {/* Bước 1 — khách hàng: chip avatar + nợ KiotViet + bảng giá (như trang tạo đơn) */}
      <div class="card co-adv-step">
        <div class="co-step-head"><span class="co-step-n">1</span> Khách hàng</div>
        {custKey && !changingCust ? (
          <div class="co-cust-picked adv">
            <span class="co-avatar" aria-hidden="true">{initial(custName || cust?.name || "?")}</span>
            <div class="co-prev-cinfo">
              <b>{custName || cust?.name || custKey}</b>
              <span class="muted small">
                {cust?.price_list_name
                  ? <>Bảng giá: {cust.price_list_name}{" "}
                      <button class="co-link" onClick={() => setPlCust(cust!.id)}>Xem giá</button></>
                  : "Giá chung"}
              </span>
            </div>
            {cust?.debt != null && (
              <span class={"co-debt" + (cust.debt > 0 ? " owe" : "")}>Nợ {money(cust.debt)}</span>
            )}
            {canChange && <button class="btn small ghost" onClick={() => setChangingCust(true)}>Đổi</button>}
          </div>
        ) : canChange ? (
          <>
            <CustomerPicker onPick={assignCustomer} placeholder={custKey ? "Tìm khách mới…" : "Gán khách cho đơn…"} />
            {changingCust
              ? <button class="btn small ghost" style="margin-top:8px" onClick={() => setChangingCust(false)}>Huỷ đổi khách</button>
              : <p class="muted small">Chưa gán khách — giá sẽ không tự lấy theo bảng giá.</p>}
          </>
        ) : (
          <p class="muted small">Chưa gán khách.</p>
        )}
      </div>

      {/* Bước 2 — sản phẩm & hoá đơn: giá tự lấy theo khách ở bước 1 */}
      <div class="co-step-head outside"><span class={"co-step-n" + (locked || editHolder ? " off" : "")}>2</span> Sản phẩm &amp; hoá đơn</div>
      {locked ? (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} />{" "}
          {hasInvoice
            ? <>Đơn đã tạo hoá đơn KiotViet ({j.kiotvietInvoiceCode || j.kiotvietInvoiceID}) — không sửa được. Muốn sửa phải xoá HĐ ở trang chi tiết trước.</>
            : <>Đơn đã <b>chốt xuất kho</b> — không sửa hoá đơn được. Admin bấm <b>Huỷ chốt</b> ở khối Xuất kho mới sửa được.</>}
        </div>
      ) : editHolder ? (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} /> <b>{editHolder}</b> đang sửa hoá đơn đơn này — chờ họ xong.
          Trang sẽ tự mở cho bạn khi họ rời.
        </div>
      ) : (
        <InvoiceEditor
          customerId={custKey || undefined}
          invoice={j.invoice || []}
          discount={j.discount}
          pvc={j.pvc}
          vat={j.vat}
          onSave={saveInvoice}
          onCancel={goBack}
        />
      )}

      {plCust && <PriceListModal customerId={plCust} onClose={() => setPlCust(null)} />}
    </div>
  );
}
