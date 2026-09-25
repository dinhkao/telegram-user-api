// Tag MÃ SP ĐANG SẢN XUẤT THAY CHỖ icon nhà máy ở ô "SX" thanh dưới (chưa có mã → icon) = mã SP của phiếu sản xuất mới nhất
// (GET /api/production/latest-sp — bỏ phiếu đóng gói/chưa chọn SP). Nhớ số cuối ở
// localStorage để hiện ngay lúc mở app; phiếu SX đổi (realtime) → tải lại (trễ 800ms).
import { useEffect, useState } from "preact/hooks";
import { getJSON } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";

const LS = "nav_sx_latest";
const readLS = () => { try { return localStorage.getItem(LS) || ""; } catch { return ""; } };

export function NavSxTag() {
  const [code, setCode] = useState(readLS);
  useEffect(() => {
    let timer: any = null;
    const load = async () => {
      try {
        const d = await getJSON("/api/production/latest-sp", { cache: false });
        const c = String(d.latest?.code || "");
        setCode(c);
        try { localStorage.setItem(LS, c); } catch { /* ignore */ }
      } catch { /* mất mạng → giữ mã cũ */ }
    };
    void load();
    const off = onRealtime((e: any) => {
      if (e.type === "production_changed" || e.type === "productions_changed" || e.type === "resync") {
        clearTimeout(timer);
        timer = setTimeout(load, 800);
      }
    });
    return () => { off(); clearTimeout(timer); };
  }, []);
  if (!code) return <Icon name="factory" size={22} class="tab-ico" />;
  // Mã dài (> 9 ký tự) thu nhỏ chữ — vẫn hiện ĐỦ, không cắt "…"
  return <span class={"tab-ico tab-sp" + (code.length > 9 ? " long" : "")} title={`Đang sản xuất: ${code}`}>{code}</span>;
}
