// Nút BACK (Android/trình duyệt) khi popup đang mở → ĐÓNG popup trước, không rời
// trang. Mỗi popup mở đẩy 1 mốc history; back tiêu vào việc đóng popup trên cùng.
// Stack cấp-module + 1 listener duy nhất → nhiều popup lồng nhau đóng đúng thứ tự.
// Dùng: usePopupBack(open, close) trong mọi component có overlay (thay/kèm useScrollLock).
import { useEffect } from "preact/hooks";

type Entry = { close: () => void };
const stack: Entry[] = [];
let installed = false;
// Số popstate cần bỏ qua do chính ta gọi history.back() lúc đóng-tay. Là ĐẾM chứ
// không phải boolean: nhiều popup unmount cùng lượt (cha đóng kéo con) → nhiều
// history.back() nối nhau trước khi popstate nào kịp chạy.
let ignoreCount = 0;

function install() {
  if (installed) return;
  installed = true;
  window.addEventListener("popstate", () => {
    if (ignoreCount > 0) { ignoreCount--; return; }
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
      const i = stack.indexOf(entry);
      // Đóng do back → listener đã pop entry + tiêu mốc history rồi, bỏ qua.
      if (i < 0) return;
      stack.splice(i, 1);
      // Đóng KHÔNG do back (tap chọn/Đóng/backdrop, hoặc CHA đóng kéo CON unmount)
      // → gỡ 1 mốc history đã đẩy. Các mốc __popup không phân biệt được nhau — gỡ
      // mốc nào cũng được miễn CÂN SỐ: mỗi entry còn trong stack gỡ đúng 1 mốc.
      // (history.back() bất đồng bộ nên history.state lúc này vẫn là mốc __popup
      // kể cả khi cleanup trước đó vừa gọi back.)
      if (history.state && history.state.__popup) {
        ignoreCount++;
        history.back();
      }
    };
  }, [open]);
}
