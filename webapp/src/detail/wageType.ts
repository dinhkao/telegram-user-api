// 3 LOẠI LƯƠNG của nhân viên (production_workers.wage_type) — gom về 1 chỗ để bảng
// lương, popup ô, hồ sơ lương thợ và trang lương thợ không lệch nhãn/luật:
//   'product'   SP   lương sản phẩm (tự tính từ báo cáo SX)
//   'time'      TG   lương thời gian: mốc/26 × ngày công + tăng ca ×1,2 TÍNH RIÊNG
//   'time_flat' TG*  CỐ ĐỊNH theo ngày công: giờ tăng ca GỘP LUÔN vào ngày công,
//                    không có tiền tăng ca riêng (luong_tc = 0)
// Luật gộp giờ TC vào công nằm ở server (salary_store/store.py) — đây chỉ là NHÃN +
// cờ hiển thị; đổi luật thì sửa cả hai.
export type WageType = "product" | "time" | "time_flat";

/** Ăn lương theo thời gian (TG hoặc TG*) → có mốc lương tháng, ngày công. */
export const isTimeWage = (wt?: WageType | string) => wt === "time" || wt === "time_flat";

/** TG*: giờ tăng ca ĐÃ gộp vào ngày công (không tính lương tăng ca riêng). */
export const otInCong = (wt?: WageType | string) => wt === "time_flat";

/** Nhãn ngắn cho ô bảng: SP · TG · TG* */
export const wageChip = (wt?: WageType | string) =>
  wt === "time_flat" ? "TG*" : wt === "time" ? "TG" : "SP";

/** Nhãn đầy đủ (view Thẻ, phụ đề trang). */
export const wageLabel = (wt?: WageType | string) =>
  wt === "time_flat" ? "Thời gian (gộp tăng ca)"
  : wt === "time" ? "Thời gian"
  : "Sản phẩm";

/** Vòng bấm đổi loại: SP → TG → TG* → SP. */
export const nextWageType = (wt?: WageType | string): WageType =>
  wt === "product" || !wt ? "time" : wt === "time" ? "time_flat" : "product";
