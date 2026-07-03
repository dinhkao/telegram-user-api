// Khối thanh toán — danh sách payment + nhập tiền TM/CK (KiotViet qua backend).
// POST /api/order/payment/tm|ck — cần mạng, không queue (chạm KiotViet + nợ).
import { useState } from "preact/hooks";
import { currentUser, postJSON } from "../api";
import { money, parseMoney } from "../format";

export function Payments({ threadId, payments, onChanged }: { threadId: string; payments: any[]; onChanged: () => void }) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const isAdmin = currentUser()?.role === "admin";

  // Xoá 1 thanh toán — chỉ admin. Payment cũ không có id thì xoá bằng lệnh Telegram.
  const del = async (p: any) => {
    if (!p.id) return alert("Thanh toán cũ không có id — xoá bằng lệnh Telegram /del_payment_");
    if (!confirm(`Xoá thanh toán ${money(p.amount)}đ?`)) return;
    setBusy(true);
    setMsg("");
    try {
      await postJSON("/api/order/payment/delete", { thread_id: Number(threadId), payment_id: p.id });
      setMsg(`🗑️ Đã xoá thanh toán ${money(p.amount)}đ`);
      onChanged();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  const pay = async (method: "tm" | "ck") => {
    const value = parseMoney(amount);
    if (!value) return alert("Nhập số tiền");
    if (!confirm(`Thu ${money(value)}đ (${method === "tm" ? "tiền mặt" : "chuyển khoản"})?`)) return;
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
      {payments.length > 0 && (
        <ul class="payment-list">
          {payments.map((p, i) => (
            <li class="row space" key={i}>
              <span>{p.code || p.method || "?"} <span class="muted small">{p.createdBy ? `· ${p.createdBy}` : ""}</span></span>
              <span class="row" style="gap:6px;align-items:center">
                <b>{money(p.amount)}đ</b>
                {isAdmin && p.id ? <button class="btn small danger" disabled={busy} title="Xoá thanh toán" onClick={() => del(p)}>🗑️</button> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
      {msg && <p class="notice" onClick={() => setMsg("")}>{msg}</p>}
      <div class="row">
        <input inputMode="numeric" placeholder="Số tiền" value={amount} onInput={(e: any) => setAmount(e.target.value)} />
        <button class="btn primary" disabled={busy} onClick={() => pay("tm")}>💵 TM</button>
        <button class="btn primary" disabled={busy} onClick={() => pay("ck")}>🏦 CK</button>
      </div>
    </div>
  );
}
