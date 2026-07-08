// Trang đăng nhập. Webapp cùng origin với server (APK nạp URL từ xa qua Tailscale)
// nên không cần nhập server URL nữa — gọi API bằng đường dẫn tương đối.
// Đã đăng nhập → trang CÀI ĐẶT (thông tin + đăng xuất; admin thêm toggle hệ thống).
import { useEffect, useState } from "preact/hooks";
import { currentUser, login, setAuth, getAppSettings, setAppSetting, type AppSettings } from "../api";
import { AppUpdate } from "../detail/AppUpdate";
import { toast } from "../ui/feedback";

/** Cài đặt hệ thống (admin): toggle rule vận hành, lưu server (kv_store). */
function AdminSettings() {
  const [st, setSt] = useState<AppSettings | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { getAppSettings().then(setSt).catch(() => setSt({})); }, []);
  if (!st) return null;
  const flip = async (key: string) => {
    setBusy(true);
    try {
      const next = await setAppSetting(key, !st[key]);
      setSt(next);
      toast(next[key] ? "Đã BẬT" : "Đã TẮT", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu cài đặt", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div class="card">
      <label class="card-label">⚙️ Cài đặt hệ thống (admin)</label>
      <label class="set-row">
        <input type="checkbox" checked={!!st.soan_hang_require_stock} disabled={busy}
          onChange={() => flip("soan_hang_require_stock")} />
        <span>Ràng buộc quy trình đơn: <b>chốt xuất kho + ảnh</b> → soạn hàng → <b>soạn xong</b> → giao hàng → <b>giao xong</b> → in hoá đơn giao</span>
      </label>
    </div>
  );
}

export function Login() {
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const user = currentUser();

  const submit = async (e: Event) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await login(username.trim(), pin);
      window.location.hash = "#/orders";
    } catch (ex: any) {
      setErr(ex.message || "Lỗi không rõ");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="login-page">
      <h1>🍬 Lê Trang Phát</h1>
      <p class="muted">Quản lý đơn hàng</p>
      {user ? (
        // Đã đăng nhập → trang cài đặt: chỉ hiện thông tin + đăng xuất (ẩn form login)
        <>
          <div class="card">
            <p>Đang đăng nhập: <b>{user.display_name}</b> ({user.username})</p>
            <div class="row">
              <a class="btn" href="#/orders">← Quay lại</a>
              <button class="btn danger" onClick={() => { setAuth("", null); window.location.reload(); }}>Đăng xuất</button>
            </div>
          </div>
          {user.role === "admin" && <AdminSettings />}
          <AppUpdate />
        </>
      ) : (
        <form onSubmit={submit} class="card">
          <label>Tên đăng nhập</label>
          <input type="text" autocapitalize="none" value={username} onInput={(e: any) => setUsername(e.target.value)} />
          <label>PIN</label>
          <input type="password" inputMode="numeric" value={pin} onInput={(e: any) => setPin(e.target.value)} />
          {err && <p class="error">{err}</p>}
          <button class="btn primary" type="submit" disabled={busy}>{busy ? "Đang vào…" : "Đăng nhập"}</button>
        </form>
      )}
    </div>
  );
}
