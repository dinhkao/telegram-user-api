// Chấm trạng thái 1 BƯỚC của đơn (Bán HĐ/Soạn/Giao/Nộp/Nhận) — thay ✅❌ emoji.
// done = vòng xanh + tick · pending = vòng xám rỗng (KHÔNG đỏ) · skip = xám + tick
// · wait = viền hổ phách (vd "chiều lấy tiền"). Trạng thái tính từ task_status.
import { Icon } from "./Icon";

export type StepState = "done" | "pending" | "skip" | "wait";

/** Suy ra trạng thái 1 bước từ task_status entry (khớp stepIcon cũ). */
export function stepState(tt: string, st: any): StepState {
  const note = String(st?.note || "").toLowerCase();
  if (tt === "nop_tien" && !st?.done && note === "chieu_lay_tien") return "wait";
  if (st?.done && st?.skip) return "skip";
  if (st?.done) return "done";
  return "pending";
}

export function StepDot({ state, size = 20 }: { state: StepState; size?: number }) {
  const cls = "stepdot " + state;
  const showCheck = state === "done" || state === "skip";
  return (
    <span class={cls} style={{ width: size, height: size }}>
      {showCheck && <Icon name="check" size={Math.round(size * 0.6)} strokeWidth={3} />}
    </span>
  );
}
