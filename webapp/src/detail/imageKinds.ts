// Phân loại ảnh đơn — nhãn/icon dùng chung cho lưới (Images) và trình xem (PhotoViewer).
import type { OrderImage } from "../api";

export const KIND_ORDER = ["soan_hang", "nop_tien", "nop_tien_task", "hoa_don", "khac"] as const;
// Lưu ý: key 'nop_tien' là NỘI BỘ (đã có dữ liệu) — nhãn hiển thị là "Nhận tiền"
// (phiếu thu = tiền NHẬN từ khách). Đừng đổi key để khỏi phải migrate.
export const KIND_LABEL: Record<string, string> = { soan_hang: "Soạn hàng", nop_tien: "Nhận tiền", nop_tien_task: "Nộp tiền", hoa_don: "Hoá đơn", khac: "Khác" };
export const KIND_ICON: Record<string, string> = { soan_hang: "📦", nop_tien: "💵", nop_tien_task: "💰", hoa_don: "🧾", khac: "🏷️" };

/** Loại hợp lệ của 1 ảnh (mặc định 'khac' nếu thiếu/lạ). */
export const kindOf = (img: OrderImage) => (img.kind && KIND_LABEL[img.kind] ? img.kind : "khac");

/** base có phải ảnh của ĐƠN HÀNG không (phân loại + bình luận chỉ cho đơn). */
export const isOrderBase = (base: string) => base.startsWith("/api/order/");
