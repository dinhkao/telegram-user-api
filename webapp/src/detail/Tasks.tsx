// Khối task đơn hàng — 5 bước (bán HĐ, soạn, giao, nộp, nhận) với nút đánh dấu /
// huỷ. POST /api/order/task (queueable offline) + /task_status/clear.
import { useState } from "preact/hooks";
import { postJSON } from "../api";
import { timeAgo } from "../format";

const TASKS: [string, string][] = [
  ["ban_hd", "Bán HĐ"],
  ["soan_hang", "Soạn hàng"],
  ["giao_hang", "Giao hàng"],
  ["nop_tien", "Nộp tiền"],
  ["nhan_tien", "Nhận tiền"],
];

export function Tasks({ threadId, taskStatus, onChanged }: { threadId: string; taskStatus: any; onChanged: () => void }) {
  const [busy, setBusy] = useState("");

  const mark = async (type: string) => {
    setBusy(type);
    try {
      const r = await postJSON("/api/order/task", { thread_id: Number(threadId), type }, { queueable: true });
      if (!r._queued) onChanged();
      else alert("📴 Đã lưu, sẽ gửi khi có mạng");
    } catch (ex: any) {
      alert(ex.message);
    } finally {
      setBusy("");
    }
  };

  const clear = async (type: string) => {
    if (!confirm("Huỷ đánh dấu bước này?")) return;
    setBusy(type);
    try {
      await postJSON(`/api/order/${threadId}/task_status/clear`, { type });
      onChanged();
    } catch (ex: any) {
      alert(ex.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <div class="card">
      <b>Tiến độ</b>
      <ul class="task-list">
        {TASKS.map(([type, label]) => {
          const st = taskStatus[type] || {};
          const done = !!st.done;
          return (
            <li class="row space" key={type}>
              <span>
                {done ? "✅" : "⬜"} {label}
                {done && st.by && <span class="muted small"> — {st.by}{st.at ? `, ${timeAgo(st.at)}` : ""}</span>}
                {st.note && <span class="muted small"> ({st.note})</span>}
              </span>
              {done ? (
                <button class="btn small" disabled={busy === type} onClick={() => clear(type)}>Huỷ</button>
              ) : (
                <button class="btn small primary" disabled={busy === type} onClick={() => mark(type)}>Xong</button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
