// 3 thao tác hồ sơ lương của 1 thợ dùng chung cho BẢNG lương tháng (#/luong-thang)
// và TRANG lương của thợ (#/luong-thang/:id): đổi loại lương SP↔thời gian, bật/tắt
// nhận lương tuần (theo tháng), sửa mốc lương tháng. Gom về đây để 2 nơi không lệch
// luật/thông báo. apply = nhận bảng tháng mới từ API; reload = tải lại (đổi hồ sơ thợ
// nằm ở bảng khác nên phải gọi lại /api/payroll/month).
import { setPayrollAdjust, updateWorker, type PayrollMonth, type PayrollRow } from "../api";
import { moneyR as money, ymLabel } from "../format";
import { toast, promptDialog } from "../ui/feedback";

const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);

export function payrollActions(ym: string, apply: (d: PayrollMonth) => void, reload: () => void) {
  const toggleType = async (r: PayrollRow) => {
    const next = r.wage_type === "time" ? "product" : "time";
    try {
      await updateWorker(r.worker_id, { wage_type: next });
      toast(next === "time" ? "→ Lương thời gian" : "→ Lương sản phẩm", "ok");
      reload();
    } catch (e: any) { toast(e?.message || "Lỗi đổi loại", "err"); }
  };
  // MỐC lương tháng (thợ lương THỜI GIAN) — lương thực = mốc/26 × công, TC ×1,2.
  // Mốc lưu THEO TỪNG THÁNG: lưu ở tháng đang xem thì áp từ tháng đó TRỞ ĐI, tháng
  // trước KHÔNG đổi (mốc tăng lương giữa năm không làm sai bảng lương đã trả).
  // Bỏ trắng = bỏ mốc riêng tháng này → kế thừa mốc gần nhất trước đó.
  const editMoc = async (r: PayrollRow) => {
    const v = await promptDialog(
      `Mốc lương ${ymLabel(ym)} của ${r.name}\nÁp dụng TỪ THÁNG NÀY TRỞ ĐI — tháng trước giữ nguyên.\nĐể trống = bỏ mốc riêng tháng này (kế thừa mốc trước đó).`,
      { initial: r.monthly_salary ? String(r.monthly_salary) : "", placeholder: "vd 6500000", okLabel: "Lưu" });
    if (v === null) return;
    const amount = num(v);
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { monthly_salary: amount }));
      toast(amount > 0 ? `Mốc ${ymLabel(ym)}: ${money(amount)}đ (từ tháng này trở đi)`
                       : `Đã bỏ mốc riêng ${ymLabel(ym)}`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu mốc lương", "err"); }
  };
  const toggleWeekly = async (r: PayrollRow) => {
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { weekly: !r.weekly }));
      toast(!r.weekly ? "BẬT nhận lương tuần (tháng này)" : "TẮT nhận lương tuần", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
  return { toggleType, editMoc, toggleWeekly };
}
