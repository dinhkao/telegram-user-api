// 3 thao tác hồ sơ lương của 1 thợ dùng chung cho BẢNG lương tháng (#/luong-thang)
// và TRANG lương của thợ (#/luong-thang/:id): đổi loại lương SP↔thời gian, bật/tắt
// nhận lương tuần (theo tháng), sửa mốc lương tháng. Gom về đây để 2 nơi không lệch
// luật/thông báo. apply = nhận bảng tháng mới từ API; reload = tải lại (đổi hồ sơ thợ
// nằm ở bảng khác nên phải gọi lại /api/payroll/month).
import { setPayrollAdjust, updateWorker, type PayrollMonth, type PayrollRow } from "../api";
import { moneyR as money, ymLabel } from "../format";
import { nextWageType, wageLabel } from "./wageType";
import { toast, promptDialog } from "../ui/feedback";

const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);

export function payrollActions(ym: string, apply: (d: PayrollMonth) => void, reload: () => void) {
  // Bấm chip Loại = ĐỔI VÒNG SP → TG → TG* → SP (3 loại lương, xem detail/wageType.ts)
  const toggleType = async (r: PayrollRow) => {
    const next = nextWageType(r.wage_type);
    try {
      await updateWorker(r.worker_id, { wage_type: next });
      toast(`→ Lương ${wageLabel(next).toLowerCase()}`, "ok");
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
  // TRỪ BHXH hằng tháng — cùng luật kế thừa với mốc, nhưng số 0 CÓ NGHĨA ("từ tháng
  // này thôi đóng") nên KHÔNG được lẫn với "bỏ đặt riêng": gõ 0 = đặt riêng bằng 0,
  // để TRỐNG = bỏ đặt riêng (gửi null) → kế thừa lại số của tháng trước đó.
  const editBhxh = async (r: PayrollRow) => {
    const v = await promptDialog(
      `Trừ BHXH ${ymLabel(ym)} của ${r.name}\nÁp dụng TỪ THÁNG NÀY TRỞ ĐI — tháng trước giữ nguyên.\nGõ 0 = từ tháng này thôi trừ. Để trống = bỏ đặt riêng (kế thừa số trước đó).`,
      { initial: r.bhxh ? String(r.bhxh) : "", placeholder: "vd 682500", okLabel: "Lưu" });
    if (v === null) return;
    const digits = String(v).replace(/[^\d]/g, "");
    const amount = digits === "" ? null : Number(digits);
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { bhxh: amount }));
      toast(amount === null ? `Đã bỏ mức BHXH riêng ${ymLabel(ym)}`
            : amount > 0 ? `Trừ BHXH ${ymLabel(ym)}: ${money(amount)}đ (từ tháng này trở đi)`
            : `${ymLabel(ym)} trở đi: KHÔNG trừ BHXH`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu mức BHXH", "err"); }
  };
  // LƯƠNG CHỜ HÀNG — tiền trả cho thời gian ngồi chờ nguyên liệu/hàng về. Bấm ô là
  // gõ số tiền, khỏi qua panel khoản như phụ cấp/ứng (mỗi tháng 1 số, không cần
  // nhiều dòng). CHỈ ăn tháng đang xem — không kế thừa, giống thưởng.
  const editChoHang = async (r: PayrollRow) => {
    const v = await promptDialog(
      `Lương chờ hàng ${ymLabel(ym)} của ${r.name}\nTiền trả cho thời gian chờ nguyên liệu/hàng về.\nĐể trống hoặc 0 = xoá khoản này.`,
      { initial: r.cho_hang ? String(r.cho_hang) : "", placeholder: "vd 300000", okLabel: "Lưu" });
    if (v === null) return;
    const amount = num(v);
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { cho_hang: amount }));
      toast(amount > 0 ? `Lương chờ hàng ${ymLabel(ym).toLowerCase()}: ${money(amount)}đ`
                       : `Đã xoá lương chờ hàng ${ymLabel(ym).toLowerCase()}`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu lương chờ hàng", "err"); }
  };
  const toggleWeekly = async (r: PayrollRow) => {
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { weekly: !r.weekly }));
      toast(!r.weekly ? "BẬT nhận lương tuần (tháng này)" : "TẮT nhận lương tuần", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
  // 2 khoản THƯỞNG bật/tắt — CHỈ ăn tháng đang xem, tháng sau tự tắt lại (cố ý:
  // thưởng là quyết định từng tháng, để nó bò sang tháng sau là trả thừa âm thầm).
  const toggleThuongCC = async (r: PayrollRow) => {
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { thuong_cc: !r.cc_on }));
      toast(!r.cc_on ? `BẬT thưởng chuyên cần ${ymLabel(ym).toLowerCase()}` : "TẮT thưởng chuyên cần", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
  const toggleThuongVS = async (r: PayrollRow) => {
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { thuong_vs: !r.vs_on }));
      toast(!r.vs_on ? `BẬT thưởng vệ sinh ${ymLabel(ym).toLowerCase()}` : "TẮT thưởng vệ sinh", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
  return { toggleType, editMoc, editBhxh, editChoHang, toggleWeekly, toggleThuongCC, toggleThuongVS };
}
