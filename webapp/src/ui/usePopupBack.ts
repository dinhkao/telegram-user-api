// Nút BACK (Android/trình duyệt) khi popup đang mở → ĐÓNG popup trước, không rời
// trang. Mỗi popup mở đẩy 1 mốc history; back tiêu vào việc đóng popup trên cùng.
// Stack cấp-module + 1 listener duy nhất → nhiều popup lồng nhau đóng đúng thứ tự.
// Dùng: usePopupBack(open, close) trong mọi component có overlay (thay/kèm useScrollLock).
import { useEffect } from "preact/hooks";

type Entry = { close: () => void };
const stack: Entry[] = [];
let installed = false;
let ignoreNext = false;   // bỏ qua popstate do chính ta gọi history.back() lúc đóng-tay

function install() {
  if (installed) return;
  installed = true;
  window.addEventListener("popstate", () => {
    if (ignoreNext) { ignoreNext = false; return; }
    const top = stack[stack.length - 1];
    if (top) { stack.pop(); top.close(); }   // back → đóng popup trên cùng
  });
}

export function usePopupBack(open: boolean, close: () => void): void {
  useEffect(() => {
    if (!open) return;
    install();
    const entry: Entry = { close };
    stack.push(entry);
    history.pushState({ __popup: true }, "");
    return () => {
      const wasTop = stack[stack.length - 1] === entry;
      const i = stack.indexOf(entry);
      if (i >= 0) stack.splice(i, 1);
      // Đóng KHÔNG do back (tap chọn/Đóng/backdrop) → gỡ mốc history đã đẩy.
      // (Đóng do back thì listener đã pop entry rồi → wasTop=false, bỏ qua.)
      if (wasTop && history.state && history.state.__popup) {
        ignoreNext = true;
        history.back();
      }
    };
  }, [open]);
}
