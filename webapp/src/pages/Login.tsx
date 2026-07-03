// Trang đăng nhập. Webapp cùng origin với server (APK nạp URL từ xa qua Tailscale)
// nên không cần nhập server URL nữa — gọi API bằng đường dẫn tương đối.
import { useState } from "preact/hooks";
import { currentUser, login, setAuth } from "../api";

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
        <div class="card">
          <p>Đang đăng nhập: <b>{user.display_name}</b> ({user.username})</p>
          <div class="row">
            <a class="btn" href="#/orders">← Quay lại</a>
            <button class="btn danger" onClick={() => { setAuth("", null); window.location.reload(); }}>Đăng xuất</button>
          </div>
        </div>
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
