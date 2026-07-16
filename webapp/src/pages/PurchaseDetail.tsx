// Chi tiết phiếu NHẬP HÀNG (#/nhap-hang/:id) — giống trang đơn/phiếu trả nhưng
// 100% local (không KiotViet): văn phòng sửa hàng nhập/ghi chú ở trang riêng; ảnh +
// trao đổi + lịch sử dùng entity media scope 'purchase'. Xoá = admin (xoá mềm).
// Nhập KHO hàng mua về: nút/summary + PurchaseGoodsModal (1 lần/phiếu, khoá sửa sau đó).
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getPurchase, deletePurchase, payPurchase, deletePurchasePayment,
  currentUser, isOffice, soVN, type PurchaseSlip,
} from "../api";
import { onRealtime } from "../realtime";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { PurchaseGoodsModal } from "../detail/PurchaseGoodsModal";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

const BOX_VI: Record<string, string> = {
  office: "Két văn phòng", bank: "Két ngân hàng", debt: "Két khách nợ", unknown: "Két chưa rõ",
};
const boxVi = (key: string) =>
  BOX_VI[key] || (key.startsWith("user:") ? `két ${key.slice(5)}` : key.startsWith("tg:") ? `két TG ${key.slice(3)}` : key);

function PaySection({ r, isAdmin, deleted, onChanged }: {
  r: PurchaseSlip; isAdmin: boolean; deleted: boolean; onChanged: () => void;
}) {
  const paid = r.paid || 0;
  const remaining = r.remaining ?? Math.round(r.total) - paid;
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const me = currentUser()?.username || "";
  useEffect(() => { if (open) setAmount(String(remaining)); }, [open]);

  const amt = parseInt(amount.replace(/[^\d]/g, ""), 10) || 0;
  const pay = async () => {
    if (amt <= 0) return toast("Nhập số tiền", "info");
    if (!(await confirmDialog(`Trả ${soVN(amt)}đ cho NCC từ két của bạn (${me})?`))) return;
    setBusy(true);
    try {
      await payPurchase(r.id, amt);
      toast("Đã trả tiền từ két của bạn", "ok");
      setOpen(false);
      onChanged();
    } catch (e: any) {
      toast(e?.message || "Trả tiền thất bại", "err");
    } finally { setBusy(false); }
  };
  const delPay = async (pid: number, a: number) => {
    if (!(await confirmDialog(`Gỡ lần trả ${soVN(a)}đ? Tiền tính lại về két.`, { danger: true }))) return;
    try {
      await deletePurchasePayment(r.id, pid);
      toast("Đã gỡ lần trả", "ok");
      onChanged();
    } catch (e: any) {
      toast(e?.message || "Gỡ thất bại", "err");
    }
  };

  return (
    <section class="card">
      <label class="card-label"><Icon name="wallet" size={15} /> Thanh toán NCC</label>
      <div class="pu-pay-sum">
        Đã trả <b class="cash-in">{soVN(paid)}đ</b>
        {remaining >= 0 ? (
          <> · Còn nợ NCC <b class={remaining > 0 ? "cash-out" : ""}>{soVN(remaining)}đ</b></>
        ) : (
          <> · <b class="cash-out">Trả dư {soVN(-remaining)}đ</b></>
        )}
        {remaining === 0 && <span class="cash-badge ok"> ✓ đã trả đủ</span>}
      </div>
      {(r.payments || []).map((p) => (
        <div key={p.id} class="pu-pay-row">
          <span class="muted small">{p.at ? `${p.at.slice(8, 10)}/${p.at.slice(5, 7)} ${p.at.slice(11, 16)}` : ""}</span>
          <span><b>{p.by_name || p.by}</b> trả từ <a class="pt-inl" href={`#/ket/${encodeURIComponent(p.box)}`}>{p.box_name || boxVi(p.box)}</a></span>
          <b class="pu-pay-amt">{soVN(p.amount)}đ</b>
          {isAdmin && !deleted && (
            <button class="icon-btn" title="Gỡ lần trả" onClick={() => delPay(p.id, p.amount)}>
              <Icon name="trash" size={13} />
            </button>
          )}
        </div>
      ))}
      {!deleted && remaining > 0 && !open && (
        <button class="btn" onClick={() => setOpen(true)}>
          <Icon name="wallet" size={14} /> Trả từ két của tôi
        </button>
      )}
      {!deleted && open && (
        <div class="pu-pay-form">
          <input class="quy-input" type="text" inputMode="numeric" value={amount}
            onInput={(e: any) => setAmount(e.currentTarget.value)} placeholder={`tối đa ${soVN(remaining)}`} />
          <div class="row">
            <button class="btn" onClick={() => setOpen(false)} disabled={busy}>Huỷ</button>
            <button class="btn primary" onClick={pay} disabled={busy}>
              {busy ? "Đang trả…" : `Trả ${amt > 0 ? soVN(amt) + "đ" : ""}`}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export function PurchaseDetail({ id }: { id: string }) {
  const [r, setR] = useState<PurchaseSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [showGoods, setShowGoods] = useState(false);
  const autoOpened = useRef(false);
  const isAdmin = currentUser()?.role === "admin";
  const office = isOffice();

  const load = () => getPurchase(id).then(setR).catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"));
  useEffect(() => { load(); }, [id]);
  // Mở modal "Nhập kho" nếu vừa tạo phiếu và người dùng chọn "Nhập kho ngay" (cờ session).
  useEffect(() => {
    if (!r || autoOpened.current) return;
    if (sessionStorage.getItem("pg_open") === String(id)) {
      sessionStorage.removeItem("pg_open");
      autoOpened.current = true;
      if (!r.goods_handled_at && office) setShowGoods(true);
    }
  }, [r]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const hit = e.type === "resync" || (e.type === "purchase_changed" && e.id === String(id));
      if (hit) { clearTimeout(t); t = setTimeout(load, 250); }
    });
    return () => { off(); clearTimeout(t); };
  }, [id]);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!r) return <Loading />;
  const deleted = !!r.deleted_at;

  const doDelete = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá phiếu nhập", "info");
    if ((r.payments || []).length > 0)
      return toast("Phiếu còn lần trả tiền — gỡ các lần trả trước khi xoá", "info");
    if (r.goods_handled_at)
      return toast("Phiếu đã nhập kho — không xoá được (hàng đã vào thùng)", "info");
    if (!(await confirmDialog("Xoá phiếu nhập này?", { danger: true }))) return;
    setBusy(true);
    try {
      await deletePurchase(Number(id));
      toast("Đã xoá phiếu nhập", "ok");
      window.location.hash = "#/nhap-hang";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá phiếu", "err");
    } finally { setBusy(false); }
  };

  return (
    <div class="ret-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/nhap-hang" />
        <div>
          <div class="prod-sp big">
            <Icon name="truck" size={18} /> Nhập hàng {soVN(r.total)}đ
          </div>
          <div class="prod-date muted">{r.created_at ? `${r.created_at.slice(8, 10)}/${r.created_at.slice(5, 7)}/${r.created_at.slice(0, 4)} ${r.created_at.slice(11, 16)}` : ""}{r.created_by ? ` · ${r.created_by}` : ""}</div>
        </div>
        {!deleted && (
          <a
            class={"btn small ret-edit" + (office && !r.goods_handled_at ? "" : " faded")}
            href={`#/nhap-hang/${id}/sua`}
            onClick={(e) => {
              if (!office) {
                e.preventDefault();
                toast("Chỉ văn phòng mới được sửa phiếu nhập", "info");
              } else if (r.goods_handled_at) {
                e.preventDefault();
                toast("Phiếu đã nhập kho — không sửa hàng được nữa", "info");
              }
            }}
          >
            <Icon name="edit" size={13} /> Sửa
          </a>
        )}
      </div>
      {deleted && <div class="error-banner">Phiếu đã bị xoá{r.deleted_by ? ` bởi ${r.deleted_by}` : ""}</div>}

      <section class="card">
        <label class="card-label"><Icon name="users" size={15} /> Nhà cung cấp</label>
        <a class="ret-cust-link" href={`#/ncc/${r.supplier_id}`}>
          {r.supplier_name || `NCC #${r.supplier_id}`} <Icon name="link" size={13} />
        </a>
      </section>

      <section class="card">
        <label class="card-label"><Icon name="box" size={15} /> Hàng nhập
        </label>
        <table class="ret-items">
          <thead><tr><th>SP</th><th>SL</th><th>Giá</th><th>Tổng</th></tr></thead>
          <tbody>
            {(r.items || []).map((x, i) => (
              <tr key={i}>
                <td>{x.sp
                      ? <a class="pt-inl" href={`#/kho/${encodeURIComponent(x.sp)}`}><b>{x.sp}</b></a>
                      : <b>{x.sp}</b>}</td>
                <td>{soVN(x.sl)}</td>
                <td>{soVN(x.price)}</td>
                <td>{soVN(x.sl * x.price)}</td>
              </tr>
            ))}
            <tr class="ret-sum"><td colSpan={3}>Tổng nhập</td><td><b>{soVN(r.total)}</b></td></tr>
          </tbody>
        </table>
        {r.note && <div class="ret-card-note"><Icon name="note" size={13} /> {r.note}</div>}
      </section>

      {!deleted && (() => {
        const gr = r.goods_result;
        if (r.goods_handled_at && gr) {
          const line = (arr: { sp: string; quantity: number; box_id: number; box_code?: string }[]) =>
            arr.map((x, i) => (
              <span key={i}>{i > 0 ? ", " : ""}{x.sp} ×{soVN(x.quantity)}{" "}
                (<a href={`#/thung/${x.box_id}`}>thùng {x.box_code || `#${x.box_id}`}</a>)</span>
            ));
          return (
            <section class="card rg-summary">
              <label class="card-label"><Icon name="check" size={15} /> Đã nhập kho</label>
              <div class="muted small">{r.goods_handled_by || ""}{r.goods_handled_at ? ` · ${r.goods_handled_at.slice(8, 10)}/${r.goods_handled_at.slice(5, 7)} ${r.goods_handled_at.slice(11, 16)}` : ""}</div>
              {gr.restocked_new?.length > 0 && <div class="rg-sum-line">🆕 Thùng mới: {line(gr.restocked_new)}</div>}
              {gr.restocked_existing?.length > 0 && <div class="rg-sum-line">📦 Nhập thùng có sẵn: {line(gr.restocked_existing)}</div>}
              {!gr.restocked_new?.length && !gr.restocked_existing?.length &&
                <div class="rg-sum-line muted">Không nhập kho mục nào (đã bỏ qua).</div>}
            </section>
          );
        }
        return (
          <button class={"btn block rg-open-btn" + (office ? "" : " faded")} disabled={busy}
            onClick={() => office ? setShowGoods(true) : toast("Chỉ văn phòng mới được nhập kho hàng mua", "info")}>
            <Icon name="box" size={15} /> Nhập kho hàng mua về
          </button>
        );
      })()}

      {showGoods && r && !r.goods_handled_at && (
        <PurchaseGoodsModal pu={r} onClose={() => setShowGoods(false)}
          onDone={(updated) => { setShowGoods(false); setR(updated); }} />
      )}

      <PaySection r={r} isAdmin={isAdmin} deleted={deleted} onChanged={load} />

      <Images base={`/api/media/purchase/${id}`} />
      <Comments base={`/api/media/purchase/${id}`} />
      <History base={`/api/media/purchase/${id}`} />

      {!deleted && (
        <button class={"btn danger block" + (isAdmin && !(r.payments || []).length && !r.goods_handled_at ? "" : " faded")}
          disabled={busy} onClick={doDelete}>
          <Icon name="trash" size={15} /> {busy ? "Đang xoá…" : "Xoá phiếu nhập"}
        </button>
      )}
    </div>
  );
}
