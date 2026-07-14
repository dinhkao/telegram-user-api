// Khối task đơn hàng — 5 bước mặc định (bán HĐ, soạn, giao, nộp, nhận) + các việc
// tự thêm (custom). Đánh dấu / huỷ: POST /api/order/task (queueable offline) +
// /task_status/clear. Thêm/xoá việc tự thêm: /api/order/{id}/custom-task[/remove].
import { useState } from "preact/hooks";
import { postJSON, isOffice, currentUser, mediaImageUrl, listMediaImages, type OrderImage } from "../api";
import { fmtTime } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { NopTienWizard } from "./NopTienWizard";
import { SoanHangPicker } from "./SoanHangPicker";
import { suggestNoTrackOldOrders } from "./suggestNoTrack";
import { PhotoViewer } from "./PhotoViewer";
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

export function Tasks({ threadId, taskStatus, stockConfirmed, customTasks, userNames, taskIds, onChanged, onAddPhoto }: { threadId: string; taskStatus: any; stockConfirmed?: boolean; customTasks?: CustomTask[]; userNames?: Record<string, string>; taskIds?: Record<string, number>; onChanged: () => void; onAddPhoto?: () => void }) {
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
      if (!r._queued) {
        onChanged();
        // Nhận tiền / Gửi toa xong → gợi ý bỏ theo dõi nợ các đơn CŨ của khách
        if (type === "nhan_tien") suggestNoTrackOldOrders(threadId);
      } else toast("📴 Đã lưu, sẽ gửi khi có mạng", "ok");
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

  // Bấm thumbnail → mở PhotoViewer (tải list ảnh đơn để vuốt qua lại như gallery)
  const [viewer, setViewer] = useState<{ images: OrderImage[]; start: number } | null>(null);
  const openImage = async (id: string) => {
    try {
      const imgs = await listMediaImages(`/api/order/${threadId}`);
      const i = imgs.findIndex((x) => x.id === Number(id));
      if (i >= 0) setViewer({ images: imgs, start: i });
      else toast("Ảnh không còn trong đơn", "info");
    } catch (e: any) { toast(e?.message || "Lỗi tải ảnh", "err"); }
  };
  const thumb = (id: string) => (
    <button class="task-thumb-btn" key={id} title="Xem ảnh" onClick={() => openImage(id)}>
      <img class="task-thumb" src={mediaImageUrl(`/api/order/${threadId}`, Number(id), "thumb")} loading="lazy" alt="" />
    </button>
  );
  // Meta = DÒNG RIÊNG dưới tên việc (người · giờ · ghi chú, rồi ảnh) — text dài
  // không đẩy nút hành động (nút neo phải, cột riêng).
  const meta = (st: any, type?: string, extra?: string) => {
    const note: string = typeof st.note === "string" ? st.note : "";
    // soạn hàng: 'imgs:1,2' — chọn từ pool. nộp tiền: '<code>;img:5' — chụp mới.
    const soanIds = type === "soan_hang" && note.startsWith("imgs:") ? note.slice(5).split(",").filter(Boolean) : null;
    let nopCode: string | null = null, nopImg: string | null = null;
    if (type === "nop_tien" && note) { const [c, rest] = note.split(";img:"); nopCode = c; nopImg = rest || null; }
    const bits: string[] = [];
    if (st.done && st.by) bits.push(`${nameOf(st.by)}${fmtTime(st.at) ? ` · ${fmtTime(st.at)}` : ""}`);
    if (nopCode) bits.push(NOP_NOTE_LABEL[nopCode] || nopCode);
    else if (note && !soanIds && !nopCode) bits.push(NOP_NOTE_LABEL[note] || note);
    if (extra) bits.push(extra);
    const thumbs = soanIds || (nopImg ? [nopImg] : null);
    if (!bits.length && !thumbs) return null;
    return (
      <div class="task-meta">
        {bits.length > 0 && <span class="muted small">{bits.join(" · ")}</span>}
        {thumbs && <span class="task-thumbs">{thumbs.map((id: string) => thumb(id))}</span>}
      </div>
    );
  };

  // Nhãn việc: LINK sang chi tiết việc (#/viec/:id) nếu có bản mirror; không thì text.
  const taskLabel = (key: string, text: string) => {
    const tid = taskIds?.[key];
    return tid
      ? <a class="task-lbl task-link" href={`#/viec/${tid}`} title="Mở chi tiết việc">{text}<Icon name="chevronRight" size={13} class="task-link-chev" /></a>
      : <span class="task-lbl">{text}</span>;
  };

  return (
    <div class="card">
      <b>Tiến độ</b>
      <ul class="task-list">
        {TASKS.map(([type, lbl]) => {
          const st = taskStatus[type] || {};
          const done = !!st.done;
          const locked = type === "nhan_tien" && !office;   // nhận tiền: chỉ văn phòng
          // Nộp tiền xong kiểu KÝ TOA → bước 'nhận tiền' = 'Gửi toa cho khách', xong 📄
          const nopNote = String((taskStatus.nop_tien || {}).note || "").toLowerCase().split(";")[0];
          const guiToa = type === "nhan_tien" && !!(taskStatus.nop_tien || {}).done && (nopNote === "co_ky_toa" || nopNote === "khong_ky_toa");
          const showLbl = guiToa ? "Gửi toa cho khách" : lbl;
          const taskNote = String(st.note || "").toLowerCase().split(";")[0];
          const doneIcon = done && (guiToa || (type === "nhan_tien" && taskNote === "gtr") ||
            (type === "nop_tien" && !st.skip && taskNote !== "tra_tien_mat")) ? "📄" : "✅";
          const pendingIcon = type === "soan_hang" && stockConfirmed ? "📦" : "⬜";
          return (
            <li class={"task-row" + (done ? " done" : "")} id={`task-${type}`} key={type}>
              <div class="task-main">
                <div class="task-head">{done ? doneIcon : pendingIcon} {taskLabel(type, showLbl)}</div>
                {meta(st, type, locked ? "🔒 chỉ văn phòng" : undefined)}
              </div>
              <div class="task-act">
                {locked ? null : done ? (
                  <button class="btn small" disabled={busy === type} onClick={() => clear(type)}>Huỷ</button>
                ) : type === "nop_tien" ? (
                  <button class="btn small primary" onClick={() => setNopOpen(true)}>Xong</button>
                ) : type === "soan_hang" ? (
                  <button class="btn small primary" onClick={() => setSoanOpen(true)}>Xong</button>
                ) : (
                  <button class="btn small primary" disabled={busy === type} onClick={() => mark(type)}>Xong</button>
                )}
              </div>
            </li>
          );
        })}
        {(customTasks || []).map((ct) => {
          const st = taskStatus[ct.id] || {};
          const done = !!st.done;
          return (
            <li class={"task-row" + (done ? " done" : "")} key={ct.id}>
              <div class="task-main">
                <div class="task-head">{done ? "✅" : "⬜"} {taskLabel(ct.id, ct.label)}</div>
                {meta(st)}
              </div>
              <div class="task-act">
                {done ? (
                  <button class="btn small" disabled={busy === ct.id} onClick={() => clear(ct.id)}>Huỷ</button>
                ) : (
                  <button class="btn small primary" disabled={busy === ct.id} onClick={() => mark(ct.id)}>Xong</button>
                )}
                <button class="btn small task-del" title="Xoá việc" disabled={busy === ct.id} onClick={() => removeCustom(ct.id)}><Icon name="trash" size={14} /></button>
              </div>
            </li>
          );
        })}
        <li class="task-row task-addrow">
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
      {/* Lối tắt admin (xong ngay bỏ qua ảnh) nằm TRONG popup — hàng task chỉ 1 nút Xong */}
      {nopOpen && <NopTienWizard threadId={threadId} onClose={() => setNopOpen(false)} onDone={onChanged}
        adminQuick={isAdmin ? () => { setNopOpen(false); mark("nop_tien"); } : undefined} />}
      {soanOpen && <SoanHangPicker threadId={threadId} onClose={() => setSoanOpen(false)} onDone={onChanged}
        onAddPhoto={onAddPhoto}
        adminQuick={isAdmin ? () => { setSoanOpen(false); mark("soan_hang"); } : undefined} />}
      {viewer && (
        <PhotoViewer images={viewer.images} start={viewer.start} base={`/api/order/${threadId}`} editable
          onKindChange={(id, kind) => setViewer((v) => (v ? { ...v, images: v.images.map((x) => (x.id === id ? { ...x, kind } : x)) } : v))}
          onClose={() => setViewer(null)} />
      )}
    </div>
  );
}
