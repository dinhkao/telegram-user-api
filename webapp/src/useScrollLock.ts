// Quy tắc CHUNG cho mọi popup/modal: khoá cuộn nền khi mở. Đếm tham chiếu để
// nhiều modal lồng nhau vẫn đúng (chỉ mở khoá khi cái cuối đóng).
// Dùng: useScrollLock(isOpen) trong component có overlay toàn màn hình.
import { useEffect } from "preact/hooks";

let lockCount = 0;

export function useScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    lockCount += 1;
    document.body.style.overflow = "hidden";
    return () => {
      lockCount = Math.max(0, lockCount - 1);
      if (lockCount === 0) document.body.style.overflow = "";
    };
  }, [active]);
}
