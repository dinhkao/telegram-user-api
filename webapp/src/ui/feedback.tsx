// Hệ phản hồi DÙNG CHUNG cho cả app — thay alert()/confirm()/prompt() native
// (lệch tông trong WebView, prompt có thể bị chặn). Gọi imperative từ bất kỳ đâu:
//   toast("Đã lưu", "ok");  toast("Lỗi mạng", "err");
//   if (await confirmDialog("Xoá ảnh này?", { danger:true })) { ... }
// <FeedbackHost/> mount MỘT lần ở main.tsx; store module + subscriber (không cần
// context). CSS: .toast-host/.toast-item + .cf-* trong styles.css.
import { useEffect, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { usePopupBack } from "./usePopupBack";

type Kind = "ok" | "err" | "info";
type Toast = { id: number; msg: string; kind: Kind };
type Confirm = { msg: string; okLabel: string; cancelLabel: string; danger: boolean; imageUrl?: string; resolve: (v: boolean) => void };

let _id = 0;
let toasts: Toast[] = [];
const toastSubs = new Set<(t: Toast[]) => void>();
const emitToasts = () => toastSubs.forEach((f) => f(toasts));

/** Hiện toast thoáng (tự tắt). kind: ok (xanh) · err (đỏ, lâu hơn) · info. */
export function toast(msg: string, kind: Kind = "info") {
  const t: Toast = { id: ++_id, msg, kind };
  toasts = [...toasts, t];
  emitToasts();
  setTimeout(() => { toasts = toasts.filter((x) => x.id !== t.id); emitToasts(); }, kind === "err" ? 3400 : 2100);
}

let current: Confirm | null = null;
const cfSubs = new Set<(c: Confirm | null) => void>();
const emitCf = () => cfSubs.forEach((f) => f(current));

/** Hộp xác nhận tuỳ biến → Promise<boolean>. Thay confirm() native.
 *  imageUrl: kèm ảnh xem trước (vd ảnh hoá đơn trước khi in). */
export function confirmDialog(msg: string, opts: { okLabel?: string; cancelLabel?: string; danger?: boolean; imageUrl?: string } = {}): Promise<boolean> {
  return new Promise((resolve) => {
    // Nếu đang có hộp khác → huỷ hộp cũ (trả false) để không kẹt.
    if (current) current.resolve(false);
    current = { msg, okLabel: opts.okLabel ?? "Đồng ý", cancelLabel: opts.cancelLabel ?? "Huỷ", danger: !!opts.danger, imageUrl: opts.imageUrl, resolve };
    emitCf();
  });
}

export function FeedbackHost() {
  const [ts, setTs] = useState<Toast[]>(toasts);
  const [cf, setCf] = useState<Confirm | null>(current);
  useEffect(() => {
    toastSubs.add(setTs); cfSubs.add(setCf);
    return () => { toastSubs.delete(setTs); cfSubs.delete(setCf); };
  }, []);
  const close = (v: boolean) => { if (current) { current.resolve(v); current = null; emitCf(); } };
  usePopupBack(!!cf, () => close(false));   // back → huỷ hộp xác nhận
  // Render THẲNG vào <body> (portal) → thoát mọi ancestor có transform/filter tạo
  // containing-block cho position:fixed, nên toast/hộp xác nhận luôn center theo viewport.
  const ui = (
    <>
      {ts.length > 0 && (
        <div class="toast-host">
          {ts.map((t) => <div key={t.id} class={`toast-item ${t.kind}`}>{t.msg}</div>)}
        </div>
      )}
      {cf && (
        <div class="cf-backdrop" onClick={() => close(false)}>
          <div class="cf-box" onClick={(e: any) => e.stopPropagation()}>
            <p class="cf-msg">{cf.msg}</p>
            {cf.imageUrl && <img class="cf-img" src={cf.imageUrl} alt="Xem trước" />}
            <div class="cf-actions">
              <button class="btn" onClick={() => close(false)}>{cf.cancelLabel}</button>
              <button class={cf.danger ? "btn danger" : "btn primary"} onClick={() => close(true)}>{cf.okLabel}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
  return typeof document !== "undefined" ? createPortal(ui, document.body) : ui;
}
