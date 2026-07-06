// Điều hướng back THÔNG MINH. Nút "←" nên quay lại nơi vừa đến, không nhảy về
// tab cố định. Nếu đã điều hướng trong app (có lịch sử) → history.back(); nếu vào
// LẠNH (deep-link từ thông báo / mở thẳng) → về fallback hash cho từng màn.
// Dùng bởi: các trang chi tiết (OrderDetail, BoxDetail, CustomerDetail…).
import { Icon } from "./ui/Icon";

let navCount = 0;
if (typeof window !== "undefined") {
  // Mỗi lần đổi hash trong app tăng đếm → biết có trang trước để quay lại không.
  window.addEventListener("hashchange", () => { navCount++; });
}

export function goBack(fallback: string) {
  if (navCount > 0) window.history.back();
  else window.location.hash = fallback;
}

export function BackLink({ fallback, label, className = "back" }: {
  fallback: string; label?: any; className?: string;
}) {
  return (
    <a
      class={className}
      href={fallback}
      onClick={(e: any) => { e.preventDefault(); goBack(fallback); }}
    >
      {label ?? <Icon name="back" size={18} />}
    </a>
  );
}
