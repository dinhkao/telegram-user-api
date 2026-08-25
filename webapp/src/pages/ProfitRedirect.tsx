// Trang cầu nối #/loi-nhuan (office) → dashboard LỢI NHUẬN HTML tại /loi-nhuan/
// (server_app/profit_routes.py). Chuyển cả cửa sổ kèm ?token= — server đóng dấu
// cookie nên các trang con của dashboard không cần token nữa; BACK từ dashboard
// quay về app (dùng location.replace, không để lại entry cầu nối trong history).
import { useEffect } from "preact/hooks";
import { getToken, isOffice, serverUrl } from "../api";
import { PageHead } from "../ui/PageHead";
import { EmptyState } from "../ui/states";

export function ProfitRedirect() {
  const ok = isOffice();
  const url = `${serverUrl()}/loi-nhuan/?token=${encodeURIComponent(getToken())}`;
  useEffect(() => {
    if (ok) location.replace(url);
  }, [ok, url]);
  return (
    <div>
      <PageHead fallback="#/home" title="Lợi nhuận" />
      {ok ? (
        <EmptyState>Đang mở dashboard lợi nhuận…</EmptyState>
      ) : (
        <EmptyState>Chỉ văn phòng được xem trang lợi nhuận.</EmptyState>
      )}
    </div>
  );
}
