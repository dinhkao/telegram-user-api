// PHỤ CẤP CÁC THÁNG TRƯỚC — khối trong popup "Thêm phụ cấp": liệt kê khoản CÒN HIỆU
// LỰC của 3 tháng gần nhất (API listPayrollAllowances sẵn có, 1 request/tháng) + nút
// "Chép" đưa nguyên khoản sang tháng đang xem. Khoản theo CÔNG THỨC (%/đơn giá×công)
// chép CẢ CÔNG THỨC → số tiền tự tính lại theo lương tháng này, không đông cứng số cũ.
// Chép xong KHÔNG đóng popup: ca thường là chép liền mấy khoản (ăn trưa + xăng xe…),
// mỗi lần chép có confirm + toast riêng. Dùng ở CẢ 3 chỗ nhập phụ cấp: popup ô P.cấp
// bảng lương (PayrollCellPopup), view Thẻ (PayrollCard), trang #/nhap-phu-cap
// (AllowanceEntry) — xem luật ĐỒNG BỘ trong EntryPanel.
import { useEffect, useState } from "preact/hooks";
import { listPayrollAllowances, type SalaryAllowance } from "../api";
import { moneyR as money, shiftYM, ymLabel } from "../format";
import { confirmDialog } from "../ui/feedback";
import { LoadingInline } from "../ui/states";

const MONTHS_BACK = 3;

/** Công thức của khoản (nếu có) — dựng lại tham số calc cho addPayrollAllowance. */
export function allowCalcOf(e: SalaryAllowance): { kind: "pct" | "day"; value: number } | null {
  return e.calc_kind === "pct" || e.calc_kind === "day"
    ? { kind: e.calc_kind, value: e.calc_value || 0 } : null;
}

/** Số tiền khi CHÉP khoản sang tháng đang xem: khoản theo công thức tính lại theo
 *  base/cong của THÁNG NÀY (gương của salary_store/allowance_calc.allowance_amount —
 *  server cũng tự tính lại lúc ghi, số này chỉ để toast/confirm nói đúng), khoản cố
 *  định giữ nguyên. ĐỪNG truyền e.amount thô — đó là số của THÁNG CŨ. */
export function copyAmount(e: SalaryAllowance, base: number, cong: number): number {
  const c = allowCalcOf(e);
  if (!c) return e.amount;
  return c.kind === "pct" ? Math.round(Math.max(0, base) * c.value / 100)
    : Math.round(c.value * Math.max(0, cong));
}

export function PrevAllowances({ ym, wid, onCopy }: {
  ym: string; wid: number;
  // chỗ gọi tự ghi khoản vào tháng ym (dùng lại addAllow sẵn có: apply + refresh + toast)
  onCopy: (e: SalaryAllowance) => Promise<void> | void;
}) {
  const [groups, setGroups] = useState<{ ym: string; items: SalaryAllowance[] }[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    setGroups(null);
    const months = Array.from({ length: MONTHS_BACK }, (_, i) => shiftYM(ym, -(i + 1)));
    Promise.all(months.map((m) => listPayrollAllowances(m, wid).catch(() => [] as SalaryAllowance[])))
      .then((ls) => {
        if (!alive) return;
        setGroups(months.map((m, i) => ({ ym: m, items: ls[i].filter((e) => !e.voided_at) }))
          .filter((g) => g.items.length));
      });
    return () => { alive = false; };
  }, [ym, wid]);

  if (groups === null) return <p class="muted small"><LoadingInline label="Đang tải phụ cấp tháng trước…" /></p>;
  if (!groups.length) return null;   // 3 tháng trước không có khoản nào → khỏi chiếm chỗ

  const copy = async (gym: string, e: SalaryAllowance) => {
    if (busy) return;
    const what = [e.note, e.calc_label || `${money(e.amount)}đ`].filter(Boolean).join(" — ");
    const ok = await confirmDialog(
      `Chép khoản "${what}" của ${ymLabel(gym).toLowerCase()} sang ${ymLabel(ym).toLowerCase()}?`
      + (e.calc_label ? `\nSố tiền sẽ TÍNH LẠI theo lương ${ymLabel(ym).toLowerCase()}, không lấy số cũ.` : ""),
      { okLabel: "Chép" });
    if (!ok) return;
    setBusy(true);
    try { await onCopy(e); } finally { setBusy(false); }
  };

  return (
    <div class="pa-prev">
      <div class="ie-head">Phụ cấp các tháng trước — bấm Chép để đưa sang {ymLabel(ym).toLowerCase()}</div>
      {groups.map((g) => (
        <div key={g.ym}>
          <div class="muted small pa-prev-ym">{ymLabel(g.ym)}</div>
          {g.items.map((e) => (
            <div class="pa-prev-row" key={e.id}>
              <b>{money(e.amount)}</b>
              <span class="pa-prev-note">
                {e.calc_label ? <span class="ua-calc">{e.calc_label}</span> : null}
                {e.calc_label && e.note ? " " : null}
                {e.note ? <span class="ua-note-txt">{e.note}</span> : null}
                {!e.calc_label && !e.note ? <span class="muted small">không ghi chú</span> : null}
              </span>
              <button class="btn small" disabled={busy} onClick={() => copy(g.ym, e)}>⧉ Chép</button>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
