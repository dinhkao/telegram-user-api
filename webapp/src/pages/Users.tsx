// Trang quản lý user (#/users) — CHỈ admin. Đổi vai trò, khoá/mở, đặt lại PIN, thêm
// user. Data: /api/users*. Không realtime (thao tác admin ít) — tải lại sau mỗi lệnh.
import { useEffect, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import {
  listUsers, createUser, setUserRole, setUserDisabled, setUserPin,
  currentUser, ROLE_LABEL, type WebUser,
} from "../api";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, confirmDialog, promptDialog } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { SelectPopup } from "../ui/SelectPopup";

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
    const pin = await promptDialog(`PIN mới cho "${u.username}":`, { placeholder: "PIN mới", type: "tel", okLabel: "Đặt PIN" });
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
        <PageHead fallback="#/orders" title="Quản lý user" />
        <EmptyState icon="🔒">Chỉ admin mới được quản lý user.</EmptyState>
      </div>
    );
  }

  return (
    <div class="detail users-page">
      <PageHead fallback="#/orders" title={<><Icon name="users" size={18} /> Quản lý user</>} />

      {err && <ErrorState msg={err} onRetry={load} />}
      {loading ? <Loading /> : (
        <>
          <section class="card">
            <label class="card-label">Thêm user</label>
            <div class="usr-form">
              <input class="quy-input" placeholder="username" value={nu} onInput={(e: any) => setNu(e.currentTarget.value)} />
              <input class="quy-input" placeholder="Tên hiển thị" value={nn} onInput={(e: any) => setNn(e.currentTarget.value)} />
              <input class="quy-input" placeholder="PIN" value={np} onInput={(e: any) => setNp(e.currentTarget.value)} />
              <SelectPopup class="usr-role" title="Vai trò" value={nr} onChange={setNr}
                options={roles.map((r) => ({ value: r, label: ROLE_LABEL[r] || r }))} />
              <button class="btn primary" disabled={adding} onClick={doAdd}>{adding ? "Đang tạo…" : <><Icon name="plus" size={16} /> Tạo</>}</button>
            </div>
          </section>

          {users.length === 0 ? <EmptyState>Chưa có user.</EmptyState> : (
            <section class="card">
              <label class="card-label">Danh sách ({users.length})</label>
              <ul class="usr-list">
                {users.map((u) => (
                  <li class={"usr-row" + (u.disabled ? " off" : "")} key={u.username}>
                    <div class="usr-main">
                      <div class="usr-name">
                        {u.display_name || u.username} <span class="muted small">@{u.username}</span>
                        {u.username === me?.username && <span class="muted small"> (bạn)</span>}
                        {u.disabled && <span class="usr-locked"> <Icon name="lock" size={13} /> khoá</span>}
                      </div>
                      <div class="usr-actions">
                        <SelectPopup class="usr-role" title="Đổi vai trò" value={u.role} disabled={busy === u.username}
                          onChange={(v) => changeRole(u, v)}
                          options={roles.map((r) => ({ value: r, label: ROLE_LABEL[r] || r }))} />
                        <button class="btn small" disabled={busy === u.username} onClick={() => resetPin(u)}><Icon name="key" size={14} /> PIN</button>
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
