// Tạo đơn mới — text tự do → POST /api/order/create (backend tự nhận khách +
// parse sản phẩm, cùng pipeline Telegram). Cần mạng (không queue).
import { useState } from "preact/hooks";
import { postJSON } from "../api";

export function CreateOrder() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!text.trim()) return setErr("Nhập nội dung đơn");
    setBusy(true);
    setErr("");
    try {
      const r = await postJSON("/api/order/create", { text: text.trim() });
      window.location.hash = `#/order/${r.thread_id}`;
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h2>➕ Tạo đơn mới</h2>
      <div class="card">
        <p class="muted small">
          Gõ như nhắn trong Telegram: tên khách + các dòng sản phẩm. Hệ thống tự nhận
          khách và parse sản phẩm; vào chi tiết đơn để sửa tiếp.
        </p>
        <textarea
          rows={10}
          placeholder={"vd:\nchị Hoa chợ Xóm Mới\n2 thùng KLC 350\n5kg C40 60"}
          value={text}
          onInput={(e: any) => setText(e.target.value)}
        />
        {err && <p class="error">{err}</p>}
        <button class="btn primary wide" disabled={busy} onClick={submit}>
          {busy ? "Đang tạo…" : "Tạo đơn"}
        </button>
        <p class="muted small">⚠️ Đơn tạo từ web chỉ nằm trong hệ thống — không tạo topic Telegram.</p>
      </div>
    </div>
  );
}
