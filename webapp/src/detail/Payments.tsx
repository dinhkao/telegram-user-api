// Khối thanh toán — danh sách payment + nhập tiền TM/CK (KiotViet qua backend).
// POST /api/order/payment/tm|ck — cần mạng, không queue (chạm KiotViet + nợ).
import { useState } from "preact/hooks";
import { currentUser, isOffice, postJSON } from "../api";
import { money, parseMoney, fmtDateTimeVN } from "../format";
import { confirmDialog, toast } from "../ui/feedback";

export function Payments({ threadId, payments, suggest, onChanged }: { threadId: string; payments: any[]; suggest?: number; onChanged: () => void }) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const isAdmin = currentUser()?.role === "admin";
  const office = isOffice();   // chỉ văn phòng được tạo thanh toán

  // Xoá 1 thanh toán — chỉ admin. Payment cũ không có id thì xoá bằng lệnh Telegram.
  const del = async (p: any) => {
    if (!p.id) { toast("Thanh toán cũ không có id — xoá bằng lệnh Telegram /del_payment_", "err"); return; }
    if (!(await confirmDialog(`Xoá thanh toán ${money(p.amount)}đ?\n(Xoá khỏi đơn; KiotViet có thể phải xoá tay)`, { danger: true }))) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await postJSON("/api/order/payment/delete", { thread_id: Number(threadId), payment_id: p.id });
      setMsg(r.kv_warning ? `🗑️ Đã xoá (local) ${money(p.amount)}đ · ⚠️ ${r.kv_warning}` : `🗑️ Đã xoá thanh toán ${money(p.amount)}đ`);
      onChanged();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  const pay = async (method: "tm" | "ck") => {
    const value = parseMoney(amount);
    if (!value) { toast("Nhập số tiền", "err"); return; }
    if (!(await confirmDialog(`Thu ${money(value)}đ (${method === "tm" ? "tiền mặt" : "chuyển khoản"})?`))) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await postJSON(`/api/order/payment/${method}`, { thread_id: Number(threadId), amount: value });
      setMsg(`✅ ${r.method_label || ""} ${money(r.amount)}đ · nợ: ${money(r.old_debt)} → ${money(r.new_debt)}`);
      setAmount("");
      onChanged();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="card">
      <b>Thanh toán</b>
      {payments.length > 0 ? (
        <ul class="payment-list">
          {payments.map((p, i) => (
            <li class="payment-item" key={i}>
              <div class="row space">
                <span>{p.code || p.method || "?"}</span>
                <span class="row" style="gap:6px;align-items:center">
                  <b>{money(p.amount)}đ</b>
                  {isAdmin && p.id ? <button class="btn small danger" disabled={busy} title="Xoá thanh toán" onClick={() => del(p)}>🗑️</button> : null}
                </span>
              </div>
              {(p.createdBy || p.created_at) && (
                <div class="muted small">
                  {p.createdBy || "?"}{p.created_at ? ` · ${fmtDateTimeVN(p.created_at)}` : ""}
                </div>
              )}
              {p.old_debt != null && p.new_debt != null && (
                <div class="pay-debt small">Nợ: {money(p.old_debt)}đ → <b>{money(p.new_debt)}đ</b></div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p class="muted small">Chưa có thanh toán nào.</p>
      )}
      {msg && <p class="notice" onClick={() => setMsg("")}>{msg}</p>}
      {office ? (
        <div class="pay-box">
          <input inputMode="numeric" placeholder="Số tiền" value={amount} onInput={(e: any) => setAmount(e.target.value)} />
          {suggest ? (
            <button type="button" class="pay-suggest" title="Điền tổng tiền hàng"
              onClick={() => setAmount(String(suggest))}>
              Tổng tiền hàng: {money(suggest)}đ
            </button>
          ) : null}
          <div class="pay-btns">
            <button class="btn primary" disabled={busy} onClick={() => pay("tm")}>💵 TM</button>
            <button class="btn primary" disabled={busy} onClick={() => pay("ck")}>🏦 CK</button>
          </div>
        </div>
      ) : (
        <p class="muted small">🔒 Chỉ văn phòng mới được tạo thanh toán.</p>
      )}
    </div>
  );
}
