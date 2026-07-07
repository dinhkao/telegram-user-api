// Khối task đơn hàng — 5 bước mặc định (bán HĐ, soạn, giao, nộp, nhận) + các việc
// tự thêm (custom). Đánh dấu / huỷ: POST /api/order/task (queueable offline) +
// /task_status/clear. Thêm/xoá việc tự thêm: /api/order/{id}/custom-task[/remove].
import { useState } from "preact/hooks";
import { postJSON, isOffice, currentUser, mediaImageUrl } from "../api";
import { fmtTime } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { NopTienWizard } from "./NopTienWizard";
import { SoanHangPicker } from "./SoanHangPicker";
import { Icon } from "../ui/Icon";

const TASKS: [string, string][] = [
  ["ban_hd", "Bán HĐ"],
  ["soan_hang", "Soạn hàng"],
  ["giao_hang", "Giao hàng"],
  ["nop_tien", "Nộp tiền"],
  ["nhan_tien", "Nhận tiền"],
];

// note nộp tiền (giống bot) → nhãn đẹp hiển thị
const NOP_NOTE_LABEL: Record<string, string> = {
  tra_tien_mat: "trả đủ · tiền mặt",
  co_ky_toa: "nợ · có ký toa",
  khong_ky_toa: "nợ · không ký toa",
  chieu_lay_tien: "nợ · chiều lấy tiền",
};

type CustomTask = { id: string; label: string };

export function Tasks({ threadId, taskStatus, customTasks, userNames, onChanged }: { threadId: string; taskStatus: any; customTasks?: CustomTask[]; userNames?: Record<string, string>; onChanged: () => void }) {
  const [busy, setBusy] = useState("");
  const [adding, setAdding] = useState(false);
  const [label, setLabel] = useState("");
  const [nopOpen, setNopOpen] = useState(false);   // wizard nộp tiền
  const [soanOpen, setSoanOpen] = useState(false); // popup chọn ảnh soạn hàng
  const office = isOffice();   // chỉ văn phòng được đánh dấu/huỷ "nhận tiền"
  const isAdmin = currentUser()?.role === "admin";   // admin: xong ngay, bỏ qua yêu cầu
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

  const addCustom = async () => {
    const l = label.trim();
    if (!l) return;
    setBusy("__add");
    try {
      await postJSON(`/api/order/${threadId}/custom-task`, { label: l });
      setLabel("");
      setAdding(false);
      onChanged();
    } catch (ex: any) {
      toast(ex.message, "err");
    } finally {
      setBusy("");
    }
  };

  const removeCustom = async (id: string) => {
    if (!(await confirmDialog("Xoá hẳn việc này khỏi đơn?", { danger: true }))) return;
    setBusy(id);
    try {
      await postJSON(`/api/order/${threadId}/custom-task/remove`, { id });
      onChanged();
    } catch (ex: any) {
      toast(ex.message, "err");
    } finally {
      setBusy("");
    }
  };

  const thumb = (id: string) => <img class="task-thumb" key={id} src={mediaImageUrl(`/api/order/${threadId}`, Number(id), "thumb")} loading="lazy" alt="" />;
  const meta = (st: any, type?: string) => {
    const note: string = typeof st.note === "string" ? st.note : "";
    // soạn hàng: 'imgs:1,2' — chọn từ pool. nộp tiền: '<code>;img:5' — chụp mới.
    const soanIds = type === "soan_hang" && note.startsWith("imgs:") ? note.slice(5).split(",").filter(Boolean) : null;
    let nopCode: string | null = null, nopImg: string | null = null;
    if (type === "nop_tien" && note) { const [c, rest] = note.split(";img:"); nopCode = c; nopImg = rest || null; }
    return (
      <>
        {st.done && st.by && <span class="muted small"> — {nameOf(st.by)}{fmtTime(st.at) ? `, ${fmtTime(st.at)}` : ""}</span>}
        {soanIds ? (
          <span class="task-thumbs">{soanIds.map((id: string) => thumb(id))}</span>
        ) : nopCode ? (
          <>
            <span class="muted small"> ({NOP_NOTE_LABEL[nopCode] || nopCode})</span>
            {nopImg && <span class="task-thumbs">{thumb(nopImg)}</span>}
          </>
        ) : note ? <span class="muted small"> ({NOP_NOTE_LABEL[note] || note})</span> : null}
      </>
    );
  };

  return (
    <div class="card">
      <b>Tiến độ</b>
      <ul class="task-list">
        {TASKS.map(([type, lbl]) => {
          const st = taskStatus[type] || {};
          const done = !!st.done;
          const locked = type === "nhan_tien" && !office;   // nhận tiền: chỉ văn phòng
          return (
            <li class="row space" id={`task-${type}`} key={type}>
              <span>
                {done ? "✅" : "⬜"} {lbl}
                {meta(st, type)}
                {locked && <span class="muted small"> 🔒 chỉ văn phòng</span>}
              </span>
              {locked ? null : done ? (
                <button class="btn small" disabled={busy === type} onClick={() => clear(type)}>Huỷ</button>
              ) : type === "nop_tien" ? (
                <span class="row" style="gap:6px">
                  <button class="btn small primary" onClick={() => setNopOpen(true)}>Xong</button>
                  {isAdmin && <button class="btn small" title="Admin: xong ngay, không cần ảnh" disabled={busy === type} onClick={() => mark(type)}><Icon name="zap" size={14} /></button>}
                </span>
              ) : type === "soan_hang" ? (
                <span class="row" style="gap:6px">
                  <button class="btn small primary" onClick={() => setSoanOpen(true)}>Xong</button>
                  {isAdmin && <button class="btn small" title="Admin: xong ngay, không cần ảnh" disabled={busy === type} onClick={() => mark(type)}><Icon name="zap" size={14} /></button>}
                </span>
              ) : (
                <button class="btn small primary" disabled={busy === type} onClick={() => mark(type)}>Xong</button>
              )}
            </li>
          );
        })}
        {(customTasks || []).map((ct) => {
          const st = taskStatus[ct.id] || {};
          const done = !!st.done;
          return (
            <li class="row space" key={ct.id}>
              <span>
                {done ? "✅" : "⬜"} {ct.label}
                {meta(st)}
              </span>
              <span class="row" style="gap:6px">
                {done ? (
                  <button class="btn small" disabled={busy === ct.id} onClick={() => clear(ct.id)}>Huỷ</button>
                ) : (
                  <button class="btn small primary" disabled={busy === ct.id} onClick={() => mark(ct.id)}>Xong</button>
                )}
                <button class="btn small" title="Xoá việc" disabled={busy === ct.id} onClick={() => removeCustom(ct.id)}><Icon name="trash" size={14} /></button>
              </span>
            </li>
          );
        })}
        <li class="row space">
          {adding ? (
            <span class="row" style="gap:6px;width:100%">
              <input class="narrow" style="flex:1" value={label} placeholder="Tên việc mới…" autofocus
                onInput={(e: any) => setLabel(e.target.value)}
                onKeyDown={(e: any) => { if (e.key === "Enter") addCustom(); if (e.key === "Escape") { setAdding(false); setLabel(""); } }} />
              <button class="btn small primary" disabled={busy === "__add" || !label.trim()} onClick={addCustom}>Thêm</button>
              <button class="btn small" disabled={busy === "__add"} onClick={() => { setAdding(false); setLabel(""); }}><Icon name="close" size={14} /></button>
            </span>
          ) : (
            <button class="btn small" onClick={() => setAdding(true)}><Icon name="plus" size={14} /> Thêm việc</button>
          )}
        </li>
      </ul>
      {nopOpen && <NopTienWizard threadId={threadId} onClose={() => setNopOpen(false)} onDone={onChanged} />}
      {soanOpen && <SoanHangPicker threadId={threadId} onClose={() => setSoanOpen(false)} onDone={onChanged} />}
    </div>
  );
}
