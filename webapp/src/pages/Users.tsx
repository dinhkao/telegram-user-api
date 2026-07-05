// Trang quản lý user (#/users) — CHỈ admin. Đổi vai trò, khoá/mở, đặt lại PIN, thêm
// user. Data: /api/users*. Không realtime (thao tác admin ít) — tải lại sau mỗi lệnh.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  listUsers, createUser, setUserRole, setUserDisabled, setUserPin,
  currentUser, ROLE_LABEL, type WebUser,
} from "../api";
import { Loading, EmptyState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";

export function Users() {
  const me = currentUser();
  const [users, setUsers] = useState<WebUser[]>([]);
  const [roles, setRoles] = useState<string[]>(["staff", "van_phong", "admin"]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  // form thêm user
  const [nu, setNu] = useState("");
  const [nn, setNn] = useState("");
  const [np, setNp] = useState("");
  const [nr, setNr] = useState("staff");
  const [adding, setAdding] = useState(false);

  const load = async () => {
    try {
      const r = await listUsers();
      setUsers(r.users);
      setRoles(r.roles);
      setErr("");
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải danh sách user");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const changeRole = async (u: WebUser, role: string) => {
    if (role === u.role) return;
    setBusy(u.username);
    try { await setUserRole(u.username, role); toast(`${u.username} → ${ROLE_LABEL[role] || role}`, "ok"); await load(); }
    catch (e: any) { toast(e?.message || "Lỗi đổi vai trò", "err"); }
    finally { setBusy(""); }
  };

  const toggleDisabled = async (u: WebUser) => {
    const next = !u.disabled;
    if (next && !(await confirmDialog(`Khoá đăng nhập của "${u.username}"?`, { danger: true, okLabel: "Khoá" }))) return;
    setBusy(u.username);
    try { await setUserDisabled(u.username, next); toast(next ? "Đã khoá" : "Đã mở khoá", "ok"); await load(); }
    catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(""); }
  };

  const resetPin = async (u: WebUser) => {
    const pin = prompt(`PIN mới cho "${u.username}":`);
    if (pin == null) return;
    if (!pin.trim()) { toast("PIN trống", "err"); return; }
    setBusy(u.username);
    try { await setUserPin(u.username, pin.trim()); toast("Đã đặt lại PIN", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi đặt PIN", "err"); }
    finally { setBusy(""); }
  };

  const doAdd = async () => {
    if (!nu.trim() || !np.trim()) { toast("Nhập username + PIN", "err"); return; }
    setAdding(true);
    try {
      await createUser(nu.trim().toLowerCase(), np.trim(), nn.trim(), nr);
      toast(`Đã tạo ${nu.trim().toLowerCase()}`, "ok");
      setNu(""); setNn(""); setNp(""); setNr("staff");
      await load();
    } catch (e: any) { toast(e?.message || "Tạo user thất bại", "err"); }
    finally { setAdding(false); }
  };

  if (me?.role !== "admin") {
    return (
      <div class="detail">
        <header class="od-appbar"><BackLink fallback="#/orders" className="od-back" /><div class="od-appttl">Quản lý user</div></header>
        <EmptyState icon="🔒">Chỉ admin mới được quản lý user.</EmptyState>
      </div>
    );
  }

  return (
    <div class="detail users-page">
      <header class="od-appbar">
        <BackLink fallback="#/orders" className="od-back" />
        <div class="od-appttl">👥 Quản lý user</div>
      </header>

      {err && <div class="error-banner">{err}</div>}
      {loading ? <Loading /> : (
        <>
          <section class="card">
            <b>Thêm user</b>
            <div class="usr-form">
              <input class="quy-input" placeholder="username" value={nu} onInput={(e: any) => setNu(e.currentTarget.value)} />
              <input class="quy-input" placeholder="Tên hiển thị" value={nn} onInput={(e: any) => setNn(e.currentTarget.value)} />
              <input class="quy-input" placeholder="PIN" value={np} onInput={(e: any) => setNp(e.currentTarget.value)} />
              <select class="usr-role" value={nr} onChange={(e: any) => setNr(e.currentTarget.value)}>
                {roles.map((r) => <option value={r} key={r}>{ROLE_LABEL[r] || r}</option>)}
              </select>
              <button class="btn primary" disabled={adding} onClick={doAdd}>{adding ? "Đang tạo…" : "➕ Tạo"}</button>
            </div>
          </section>

          {users.length === 0 ? <EmptyState>Chưa có user.</EmptyState> : (
            <section class="card">
              <b>Danh sách ({users.length})</b>
              <ul class="usr-list">
                {users.map((u) => (
                  <li class={"usr-row" + (u.disabled ? " off" : "")} key={u.username}>
                    <div class="usr-main">
                      <div class="usr-name">
                        {u.display_name || u.username} <span class="muted small">@{u.username}</span>
                        {u.username === me?.username && <span class="muted small"> (bạn)</span>}
                        {u.disabled && <span class="usr-locked"> 🔒 khoá</span>}
                      </div>
                      <div class="usr-actions">
                        <select class="usr-role" value={u.role} disabled={busy === u.username}
                          onChange={(e: any) => changeRole(u, e.currentTarget.value)}>
                          {roles.map((r) => <option value={r} key={r}>{ROLE_LABEL[r] || r}</option>)}
                        </select>
                        <button class="btn small" disabled={busy === u.username} onClick={() => resetPin(u)}>🔑 PIN</button>
                        <button class="btn small" disabled={busy === u.username} onClick={() => toggleDisabled(u)}>
                          {u.disabled ? "Mở" : "Khoá"}
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
