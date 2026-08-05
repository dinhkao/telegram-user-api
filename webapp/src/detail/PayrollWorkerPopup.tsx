// POPUP HỒ SƠ LƯƠNG THÁNG của 1 thợ — bấm ô TÊN ở bảng lương (#/luong-thang) mở
// cái này, KHÔNG rời trang nữa (trước là nhảy sang trang #/luong-thang/:id, xem xong
// phải back → mất chỗ đang cuộn + phải tải lại cả bảng).
// Nội dung dùng CHUNG detail/PayrollWorkerSheet với trang riêng (trang vẫn giữ để
// chia sẻ link / mở tab mới), nên sửa nội dung chỉ sửa 1 chỗ.
// Bấm 1 khối trong sheet → mở tiếp PayrollCellPopup đúng tab (popup chồng popup:
// cell popup render SAU nên nằm trên).
import { useState } from "preact/hooks";
import { payslipMonthHtmlUrl, type PayrollMonth, type PayrollRow } from "../api";
import { PayrollWorkerSheet } from "./PayrollWorkerSheet";
import { PayrollCellPopup, type PayrollCol } from "./PayrollCellPopup";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { ymLabel } from "../format";
import { wageLabel } from "./wageType";

export function PayrollWorkerPopup({ ym, r, onClose, apply, toggleType, toggleWeekly, editMoc, editBhxh }: {
  ym: string; r: PayrollRow;
  onClose: () => void;
  apply: (d: PayrollMonth) => void;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  editMoc: (r: PayrollRow) => void; editBhxh: (r: PayrollRow) => void;
}) {
  // BACK đóng popup con (ô) trước, hết mới đóng popup hồ sơ — usePopupBack của
  // PayrollCellPopup đăng ký sau nên nó nhận BACK trước, đúng thứ tự người dùng mong
  usePopupBack(true, onClose);
  useScrollLock(true);
  const [col, setCol] = useState<PayrollCol | null>(null);

  return (
    <>
      <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
        <div class="modal-sheet pr-pop-sheet pws-popup" onClick={(e: any) => e.stopPropagation()}>
          <div class="modal-head">
            <Icon name="wallet" size={18} />
            <span class="pws-popup-title">{r.name}</span>
            <span class="muted small">lương {wageLabel(r.wage_type).toLowerCase()} · {ymLabel(ym).toLowerCase()}</span>
            {/* PHIẾU LƯƠNG THÁNG in giấy (khổ hoá đơn) — tab mới, không rời bảng lương */}
            <button class="pws-popup-print" title="In phiếu lương tháng"
              onClick={() => window.open(payslipMonthHtmlUrl(r.worker_id, ym), "_blank")}>
              <Icon name="printer" size={16} /> In phiếu
            </button>
            {/* mở TRANG riêng khi cần link chia sẻ / xem cạnh nhau */}
            <a class="pws-popup-open" href={`#/luong-thang/${r.worker_id}?ym=${encodeURIComponent(ym)}`}
              title="Mở thành trang riêng">↗</a>
          </div>
          <PayrollWorkerSheet ym={ym} r={r} onCol={setCol}
            toggleType={toggleType} toggleWeekly={toggleWeekly} />
          <button class="btn sh-cancel" onClick={onClose}>Đóng</button>
        </div>
      </div>
      {col && (
        <PayrollCellPopup ym={ym} r={r} col={col}
          onClose={() => setCol(null)} onCol={setCol}
          apply={apply} editMoc={editMoc} editBhxh={editBhxh} />
      )}
    </>
  );
}
