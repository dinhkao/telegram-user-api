// Chi tiết phiếu NHẬP HÀNG (#/nhap-hang/:id) — giống trang đơn/phiếu trả nhưng
// 100% local (không KiotViet): văn phòng sửa hàng nhập/ghi chú ở trang riêng; ảnh +
// trao đổi + lịch sử dùng entity media scope 'purchase'. Xoá = admin (xoá mềm).
// Nhập KHO hàng mua về: nút/summary + PurchaseGoodsModal (1 lần/phiếu, khoá sửa sau đó).
import { useEffect, useRef, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import { fmtDateTimeVN } from "../format";
import {
  getPurchase, deletePurchase, payPurchase, deletePurchasePayment, undoPurchaseGoods,
  confirmPurchaseGoods, unreceivePurchase, deleteBox, currentUser, soVN,
  type PurchaseSlip, type PurchaseDraftLine,
} from "../api";
import { onRealtime } from "../realtime";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";
import { BoxTileGrid, type BoxTileData } from "../detail/BoxTileGrid";
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
          <span class="muted small">{fmtDateTimeVN(p.at)}</span>
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
  // Tạo/sửa/nhập kho phiếu nhập mở cho MỌI người dùng (2026-07-17) — chỉ còn
  // admin cho xoá phiếu / hủy chốt / gỡ lần trả tiền.

  const load = () => getPurchase(id).then(setR).catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"));
  useEffect(() => { load(); }, [id]);
  // Mở modal "Nhập kho" nếu vừa tạo phiếu và người dùng chọn "Nhập kho ngay" (cờ session).
  useEffect(() => {
    if (!r || autoOpened.current) return;
    if (sessionStorage.getItem("pg_open") === String(id)) {
      sessionStorage.removeItem("pg_open");
      autoOpened.current = true;
      if (!r.goods_handled_at) setShowGoods(true);
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

  const draftLines = (r.draft_receipt?.new.length || 0) + (r.draft_receipt?.existing.length || 0);
  const doDelete = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá phiếu nhập", "info");
    if ((r.payments || []).length > 0)
      return toast("Phiếu còn lần trả tiền — gỡ các lần trả trước khi xoá", "info");
    if (r.goods_handled_at)
      return toast("Phiếu đã nhập kho — không xoá được (hàng đã vào thùng)", "info");
    if (draftLines > 0)
      return toast("Phiếu đang nhập kho dở — xoá thùng/gỡ dòng nhập trước khi xoá phiếu", "info");
    if (!(await confirmDialog("Xoá phiếu nhập này?", { danger: true, okLabel: "Xoá phiếu" }))) return;
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
      <PageHead fallback="#/nhap-hang"
        title={<><Icon name="truck" size={18} /> Nhập hàng {soVN(r.total)}đ</>}
        sub={<>{fmtDateTimeVN(r.created_at)}{r.created_by ? ` · ${r.created_by}` : ""}</>}
        right={!deleted && (
          <a
            class={"btn small ret-edit" + (!r.goods_handled_at ? "" : " faded")}
            href={`#/nhap-hang/${id}/sua`}
            onClick={(e) => {
              // Sửa phiếu mở cho mọi người dùng (2026-07-17) — chỉ khoá khi đã chốt kho
              if (r.goods_handled_at) {
                e.preventDefault();
                toast("Phiếu đã nhập kho — không sửa hàng được nữa", "info");
              }
            }}
          >
            <Icon name="edit" size={13} /> Sửa
          </a>
        )} />
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
                <td>{soVN(x.sl)}{(x.unit || x.base_unit) ? <span class="muted"> {x.unit || x.base_unit}</span> : ""}
                  {x.unit && (x.unit_factor || 0) > 0
                    ? <div class="muted small">= {soVN(x.sl * (x.unit_factor || 1))}{x.base_unit ? ` ${x.base_unit}` : ""}</div> : null}</td>
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
        const line = (arr: { sp: string; quantity: number; box_id: number; box_code?: string; box_deleted?: boolean }[]) =>
          arr.map((x, i) => (
            <span key={i}>{i > 0 ? ", " : ""}{x.sp} ×{soVN(x.quantity)}{" "}
              {x.box_deleted
                ? <span class="muted strike">(thùng {x.box_code || `#${x.box_id}`} — đã xoá)</span>
                : <>(<a href={`#/thung/${x.box_id}`}>thùng {x.box_code || `#${x.box_id}`}</a>)</>}</span>
          ));
        if (r.goods_handled_at && gr) {
          const doUndo = async () => {
            if (!(await confirmDialog(
              "Hủy chốt nhập kho phiếu này?\nCác thùng mới sẽ được GIỮ NGUYÊN để xóa từng thùng hoặc nhập bổ sung. Phần đã cộng vào thùng có sẵn sẽ bị trừ lại. Chỉ được khi hàng CHƯA dùng vào đâu.",
              { danger: true, okLabel: "Hủy chốt" }))) return;
            setBusy(true);
            try {
              await undoPurchaseGoods(r.id);
              toast("Đã hủy chốt nhập kho — phiếu sửa lại được", "ok");
              load();
            } catch (e: any) {
              toast(e?.message || "Không hủy chốt được", "err");
            } finally { setBusy(false); }
          };
          return (
            <section class="card rg-summary">
              <label class="card-label"><Icon name="check" size={15} /> Đã nhập kho
                {isAdmin && (
                  <button class="btn small rg-undo-btn" disabled={busy} onClick={doUndo}
                    title="Giữ nguyên thùng mới và mở khóa phiếu — chặn nếu hàng đã dùng">
                    <Icon name="refresh" size={13} /> Hủy chốt
                  </button>
                )}
              </label>
              <div class="muted small">{r.goods_handled_by || ""}{r.goods_handled_at ? ` · ${fmtDateTimeVN(r.goods_handled_at)}` : ""}</div>
              {gr.restocked_new?.length > 0 && <div class="rg-sum-line">🆕 Thùng mới: {line(gr.restocked_new)}</div>}
              {gr.restocked_existing?.length > 0 && <div class="rg-sum-line">📦 Nhập thùng có sẵn: {line(gr.restocked_existing)}</div>}
              {!gr.restocked_new?.length && !gr.restocked_existing?.length &&
                <div class="rg-sum-line muted">Không nhập kho mục nào (đã bỏ qua).</div>}
              {(r.boxes || []).length > 0 && (
                <div class="rg-boxes"><BoxLabelGrid boxes={r.boxes as any} dense /></div>
              )}
            </section>
          );
        }
        // Phiếu ĐANG MỞ: nhập kho TỪNG ĐỢT như xuất kho cho đơn — trạng thái
        // đang nhập (draft_receipt) derive live từ kho; ✕ góc ô thùng xoá thùng
        // mới / gỡ từng lần cộng (như thu hồi ở OrderStock); đủ rồi CHỐT mới khoá.
        const draft = r.draft_receipt;
        const hasDraft = !!draft && draft.new.length + draft.existing.length > 0;
        // Khớp dòng phiếu ↔ đã-nhập theo DANH TÍNH SP (sp_id — mã đổi tên giữa
        // chừng vẫn khớp, cùng luật _product_key server), fallback mã uppercase.
        const spKey = (sp?: string | null, id?: number | null) => (id ? `#${id}` : (sp || "").toUpperCase());
        const baseBySp = new Map<string, { code: string; base: number }>();
        for (const it of r.items || []) {
          const f = it.unit && (it.unit_factor || 0) > 0 ? it.unit_factor! : 1;
          const k = spKey(it.sp, it.sp_id);
          const cur = baseBySp.get(k) || { code: (it.sp || "").toUpperCase(), base: 0 };
          cur.base += it.sl * f;
          baseBySp.set(k, cur);
        }
        const gotBySp = new Map<string, number>();
        for (const t of draft?.totals || []) {
          const k = spKey(t.sp, t.sp_id);
          gotBySp.set(k, (gotBySp.get(k) || 0) + Number(t.quantity || 0));
        }
        const missing = [...baseBySp.entries()]
          .map(([k, { code, base }]) => ({ code, base, got: gotBySp.get(k) || 0 }))
          .filter((x) => x.got + 1e-6 < x.base);
        const doDeleteBox = async (x: PurchaseDraftLine) => {
          const name = `thùng ${x.box_code || `#${x.box_id}`}`;
          if (!(await confirmDialog(
            `Xoá HẲN ${name} (${x.sp} ×${soVN(x.quantity)}) khỏi kho? Không thể hoàn tác.`,
            { danger: true, okLabel: "Xoá thùng" }))) return;
          setBusy(true);
          try {
            await deleteBox(x.box_id);
            toast(`Đã xoá ${name}`, "ok");
            load();
          } catch (e: any) {
            toast(e?.message || "Không xoá được thùng", "err");
          } finally { setBusy(false); }
        };
        const doUnreceive = async (x: PurchaseDraftLine) => {
          if (!x.allocation_id) return;
          if (!(await confirmDialog(
            `Gỡ ${soVN(x.quantity)} ${x.sp} đã cộng vào thùng ${x.box_code || `#${x.box_id}`}?`,
            { danger: true, okLabel: "Gỡ" }))) return;
          setBusy(true);
          try {
            const { purchase: updated } = await unreceivePurchase(r.id, x.allocation_id);
            toast("Đã gỡ dòng nhập kho", "ok");
            setR(updated);
          } catch (e: any) {
            toast(e?.message || "Không gỡ được", "err");
          } finally { setBusy(false); }
        };
        // 1 ô thùng / 1 dòng nhập (như OrderStock 1 ô / 1 allocation): thùng mới
        // ✕ = xoá hẳn thùng; cộng vào thùng có sẵn ✕ = gỡ allocation purchase_in.
        type DraftTile = BoxTileData & { line: PurchaseDraftLine; isNew: boolean };
        const boxById = new Map<number, any>(((r.boxes || []) as any[]).map((b) => [b.id, b]));
        const draftTiles: DraftTile[] = [
          ...(draft?.new || []).map((x) => ({ x, isNew: true })),
          ...(draft?.existing || []).map((x) => ({ x, isNew: false })),
        ].map(({ x, isNew }) => {
          const b = boxById.get(x.box_id) || {};
          const code = b.box_code || x.box_code || `#${x.box_id}`;
          return {
            id: x.allocation_id ? `a${x.allocation_id}` : `b${x.box_id}`,
            productCode: b.product_code || x.sp,
            boxCode: code,
            quantity: b.quantity ?? x.quantity,
            allocated: x.quantity,
            note: b.note,
            placeName: b.place_name,
            productUnit: b.product_unit,
            // vai 👁 — số trên ô quy đổi theo đơn vị hiển thị (b từ get_box đã có field)
            displayUnitName: b.display_unit_name,
            displayUnitFactor: b.display_unit_factor,
            href: `#/thung/${x.box_id}`,
            title: (isNew ? "🆕 thùng mới" : "📦 cộng vào thùng có sẵn")
              + ` · ${code} · ${isNew ? "×" : "+"}${soVN(x.quantity)} ${x.sp}${b.place_name ? ` · ${b.place_name}` : ""}`,
            line: x, isNew,
          };
        });
        // Nhập ĐỦ mọi mã theo phiếu mới chốt được (như chốt xuất kho đơn — server
        // cũng chặn). Hàng về thiếu/vỡ → sửa SL trên phiếu về số thực nhận rồi chốt.
        const confirmBlock = !hasDraft
          ? "Chưa nhập kho mục nào — nhập đủ hàng vào kho rồi mới chốt được"
          : missing.length
            ? `Chưa nhập đủ: ${missing.map((m) => `${m.code} thiếu ${soVN(m.base - m.got)}`).join(", ")} — nhập thêm cho đủ (hàng về thiếu/vỡ thì sửa SL trên phiếu)`
            : "";
        const doConfirm = async () => {
          if (confirmBlock) return toast(confirmBlock, "info");
          if (!(await confirmDialog(
            "Chốt nhập kho? Phiếu sẽ KHOÁ sửa (chỉ admin hủy chốt được).",
            { okLabel: "Chốt nhập kho" }))) return;
          setBusy(true);
          try {
            const { purchase: updated } = await confirmPurchaseGoods(r.id);
            toast("Đã chốt nhập kho", "ok");
            setR(updated);
          } catch (e: any) {
            toast(e?.message || "Không chốt được", "err");
          } finally { setBusy(false); }
        };
        return (
          <>
            {hasDraft && (
              <section class="card rg-summary">
                <label class="card-label"><Icon name="box" size={15} /> Đang nhập kho (chưa chốt)</label>
                <div class="muted small">
                  {[...baseBySp.entries()].map(([k, { code, base }]) => {
                    const got = gotBySp.get(k) || 0;
                    return (
                      <div key={k}>
                        {code}: đã nhập <b>{soVN(got)}</b> / {soVN(base)}
                        {got + 1e-6 < base ? ` · còn thiếu ${soVN(base - got)}` : " · ✓ đủ"}
                      </div>
                    );
                  })}
                </div>
                {draftTiles.length > 0 && (
                  <div class="rg-boxes">
                    <BoxTileGrid
                      size="dense"
                      mode="allocated"
                      productCodeMode="auto"
                      boxes={draftTiles}
                      getAction={(t) => ({
                        label: t.isNew ? "Xoá hẳn thùng này khỏi kho" : "Gỡ phần đã cộng vào thùng",
                        content: <Icon name="close" size={12} />,
                        disabled: busy,
                        onClick: () => (t.isNew ? doDeleteBox(t.line) : doUnreceive(t.line)),
                      })}
                    />
                  </div>
                )}
              </section>
            )}
            <div class="row">
              <button class="btn block rg-open-btn" disabled={busy}
                onClick={() => setShowGoods(true)}>
                <Icon name="box" size={15} /> {hasDraft ? "Nhập thêm" : "Nhập kho hàng mua về"}
              </button>
              <button class={"btn primary block" + (!confirmBlock ? "" : " faded")} disabled={busy}
                title={confirmBlock || undefined}
                onClick={doConfirm}>
                ✓ Chốt nhập kho
              </button>
            </div>
          </>
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
        <button class={"btn danger block" + (isAdmin && !(r.payments || []).length && !r.goods_handled_at && !draftLines ? "" : " faded")}
          disabled={busy} onClick={doDelete}>
          <Icon name="trash" size={15} /> {busy ? "Đang xoá…" : "Xoá phiếu nhập"}
        </button>
      )}
    </div>
  );
}
