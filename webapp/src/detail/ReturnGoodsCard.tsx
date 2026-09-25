// Khối XỬ LÝ HÀNG của phiếu trả (#/tra-hang/:id): các dòng đã xử lý (thùng mới / nhập
// thùng có sẵn / xuất hủy) mỗi dòng có nút Gỡ (văn phòng) — server chỉ cho gỡ khi hàng
// chưa đi đâu (server_app/return_goods_edit). Phần CHƯA xử lý (goods_pending) hiện
// riêng kèm nút "Xử lý tiếp" (mở ReturnGoodsModal với đúng phần còn lại).
import { useState } from "preact/hooks";
import { revertReturnGoods, soVN, type ReturnSlip } from "../api";
import { fmtDateTimeVN } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";

type Kind = "restocked_new" | "restocked_existing" | "disposed";
const LABEL: Record<Kind, string> = {
  restocked_new: "Thùng mới", restocked_existing: "Nhập thùng có sẵn", disposed: "Xuất hủy",
};
const ICON: Record<Kind, string> = { restocked_new: "plus", restocked_existing: "box", disposed: "trash" };
const CONFIRM: Record<Kind, string> = {
  restocked_new: "Xoá thùng mới này khỏi kho",
  restocked_existing: "Trừ lại phần hàng trả đã cộng vào thùng này",
  disposed: "Rút dòng này khỏi phiếu xuất hủy",
};

export function ReturnGoodsCard({ r, office, locked, onChanged, onHandle }: {
  r: ReturnSlip; office: boolean;
  locked: boolean;                    // phiếu đã xoá → chỉ xem
  onChanged: (u: ReturnSlip) => void;
  onHandle: () => void;               // mở popup xử lý (lần đầu / xử lý tiếp)
}) {
  const [busy, setBusy] = useState("");
  const gr = r.goods_result;
  const pending = r.goods_pending || [];
  const lines: { kind: Kind; i: number; code: string; qty: number; box?: string; disposal?: number | null }[] = [];
  if (r.goods_handled_at && gr) {
    (["restocked_new", "restocked_existing", "disposed"] as Kind[]).forEach((kind) =>
      ((gr as any)[kind] || []).forEach((x: any, i: number) => lines.push({
        kind, i, code: x.sp || x.product_code, qty: x.quantity, box: x.box_code,
        disposal: kind === "disposed" ? (x.disposal_id ?? gr.disposal_id) : undefined,
      })));
  }

  const revert = async (l: (typeof lines)[number]) => {
    if (!office) return toast("Chỉ văn phòng mới được sửa xử lý hàng trả", "info");
    const what = `${l.code} ×${soVN(l.qty)}${l.box ? ` (thùng ${l.box})` : ""}`;
    if (!(await confirmDialog(`${CONFIRM[l.kind]}: ${what}? Phần này sẽ thành "chưa xử lý" để xử lý lại hoặc sửa phiếu.`,
      { danger: true, okLabel: "Gỡ dòng này" }))) return;
    setBusy(`${l.kind}-${l.i}`);
    try {
      onChanged(await revertReturnGoods(r.id, l.kind, l.i));
      toast("Đã gỡ — phần hàng này đang chờ xử lý lại", "ok");
    } catch (e: any) {
      toast(e?.message || "Không gỡ được", "err");
    } finally { setBusy(""); }
  };

  const handleBtn = (label: string) => (
    <button class={"btn block rg-open-btn" + (office ? "" : " faded")} disabled={!!busy}
      onClick={() => office ? onHandle() : toast("Chỉ văn phòng mới được xử lý hàng trả", "info")}>
      <Icon name="box" size={15} /> {label}
    </button>
  );

  if (!lines.length) {
    if (locked) return null;
    return handleBtn("Xử lý hàng trả về (nhập kho / xuất hủy)");
  }
  return (
    <section class="card rg-summary">
      <label class="card-label"><Icon name="check" size={15} /> Hàng trả đã xử lý</label>
      <div class="muted small">{r.goods_handled_by || ""}{r.goods_handled_at ? ` · ${fmtDateTimeVN(r.goods_handled_at)}` : ""}</div>
      {lines.map((l) => (
        <div class="rg-sum-line rg-line" key={`${l.kind}-${l.i}`}>
          <span class="rg-line-txt">
            <Icon name={ICON[l.kind]} size={13} /> {LABEL[l.kind]}: <b>{l.code}</b> ×{soVN(l.qty)}
            {l.box ? <> · thùng {l.box}</> : null}
            {l.disposal ? <> · <a href={`#/xuat-huy/${l.disposal}`}>phiếu hủy #{l.disposal}</a></> : null}
          </span>
          {!locked && (
            <button class={"btn small" + (office ? "" : " faded")} disabled={!!busy} onClick={() => revert(l)}
              title="Gỡ dòng này (chỉ khi hàng chưa xuất/chuyển/dùng)">
              <Icon name="back" size={13} /> {busy === `${l.kind}-${l.i}` ? "…" : "Gỡ"}
            </button>
          )}
        </div>
      ))}
      {!locked && pending.length > 0 && (
        <div class="rg-pending">
          <div class="t-warn small"><b>Chưa xử lý:</b> {pending.map((p) => `${p.sp} ×${soVN(p.quantity)}`).join(", ")}</div>
          {handleBtn("Xử lý tiếp phần còn lại")}
        </div>
      )}
    </section>
  );
}
