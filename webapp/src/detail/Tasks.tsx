// Khối task đơn hàng — 5 bước (bán HĐ, soạn, giao, nộp, nhận) với nút đánh dấu /
// huỷ. POST /api/order/task (queueable offline) + /task_status/clear.
import { useState } from "preact/hooks";
import { postJSON, isOffice } from "../api";
import { fmtTime } from "../format";
import { confirmDialog, toast } from "../ui/feedback";

const TASKS: [string, string][] = [
  ["ban_hd", "Bán HĐ"],
  ["soan_hang", "Soạn hàng"],
  ["giao_hang", "Giao hàng"],
  ["nop_tien", "Nộp tiền"],
  ["nhan_tien", "Nhận tiền"],
];

export function Tasks({ threadId, taskStatus, userNames, onChanged }: { threadId: string; taskStatus: any; userNames?: Record<string, string>; onChanged: () => void }) {
  const [busy, setBusy] = useState("");
  const office = isOffice();   // chỉ văn phòng được đánh dấu/huỷ "nhận tiền"
  const nameOf = (by: any) => (by == null ? "" : (userNames && userNames[String(by)]) || String(by));

  const mark = async (type: string) => {
    setBusy(type);
    try {
      const r = await postJSON("/api/order/task", { thread_id: Number(threadId), type }, { queueable: true });
      if (!r._queued) onChanged();
      else toast("📴 Đã lưu, sẽ gửi khi có mạng", "ok");
    } catch (ex: any) {
      toast(ex.message, "err");
    } finally {
      setBusy("");
    }
  };

  const clear = async (type: string) => {
    if (!(await confirmDialog("Huỷ đánh dấu bước này?", { danger: true }))) return;
    setBusy(type);
    try {
      await postJSON(`/api/order/${threadId}/task_status/clear`, { type });
      onChanged();
    } catch (ex: any) {
      toast(ex.message, "err");
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
          const locked = type === "nhan_tien" && !office;   // nhận tiền: chỉ văn phòng
          return (
            <li class="row space" key={type}>
              <span>
                {done ? "✅" : "⬜"} {label}
                {done && st.by && <span class="muted small"> — {nameOf(st.by)}{fmtTime(st.at) ? `, ${fmtTime(st.at)}` : ""}</span>}
                {st.note && <span class="muted small"> ({st.note})</span>}
                {locked && <span class="muted small"> 🔒 chỉ văn phòng</span>}
              </span>
              {locked ? null : done ? (
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
