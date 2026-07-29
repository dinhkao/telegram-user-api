// POPUP GIỜ CHẤM CỦA 1 NGÀY (1 thợ) — xem giờ máy + giờ thêm tay; văn phòng còn
// ẩn/hiện giờ máy, thêm/xoá giờ tay (canEdit). Giờ MÁY không sửa trực tiếp: ẩn giờ
// sai rồi thêm giờ đúng → lần đồng bộ sau máy không đè phần sửa.
// Dùng chung: pages/AttendanceBoard (lưới cả xưởng) + pages/WorkerAttendance
// (chấm công 1 thợ trong tháng). API: getAttendanceDay/addAttendanceManual/
// deleteAttendanceManual/suppressAttendance (server chặn office cho phần sửa).
import { useEffect, useState } from "preact/hooks";
import {
  addAttendanceManual, deleteAttendanceManual, getAttendanceDay, suppressAttendance,
  type AttendanceDayDetail,
} from "../api";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { LoadingInline, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";

export function CellEditor({ code, who, day, canEdit, onClose, onChanged }: {
  code: string; who: string; day: string; canEdit: boolean; onClose: () => void; onChanged: () => void;
}) {
  const [det, setDet] = useState<AttendanceDayDetail | null>(null);
  const [loadErr, setLoadErr] = useState(false);
  const [newTime, setNewTime] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);
  // Lỗi tải KHÔNG được giả làm "rỗng" — người dùng sẽ tưởng chưa chấm mà sửa nhầm.
  const reload = () => { setLoadErr(false); return getAttendanceDay(code, day).then(setDet).catch(() => { setDet(null); setLoadErr(true); }); };
  useEffect(() => { reload(); }, [code, day]);

  const run = async (fn: () => Promise<any>, okMsg: string): Promise<boolean> => {
    if (busy) return false;
    setBusy(true);
    try {
      await fn();
      toast(okMsg, "ok");
      await reload();
      onChanged();
      return true;
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
      return false;
    } finally {
      setBusy(false);
    }
  };
  const addTime = async () => {
    if (!newTime) return;
    // Chỉ xoá ô nhập KHI lưu thành công — hỏng thì giữ lại để khỏi gõ lại.
    if (await run(() => addAttendanceManual(code, day, newTime), `Đã thêm giờ ${newTime}`)) setNewTime("");
  };
  const [y, m, d] = day.split("-");
  return (
    <div class="att-ed-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="att-ed" role="dialog" aria-modal="true" aria-label={`${canEdit ? "Sửa" : "Xem"} giờ chấm — ${who}`}>
        <div class="att-ed-head">
          <b>{who}</b>
          <span class="muted">{Number(d)}/{Number(m)}/{y}</span>
          <button class="icon-btn att-ed-x" onClick={onClose} title="Đóng" aria-label="Đóng cửa sổ sửa chấm công">✕</button>
        </div>
        {loadErr ? <ErrorState msg="Không tải được giờ chấm ngày này" onRetry={reload} />
          : det === null ? <LoadingInline /> : (
          <>
            <div class="att-ed-sec">Giờ máy chấm {det.machine.length === 0 && <span class="muted small">— không có</span>}</div>
            {det.machine.map((mrow) => (
              <div class={"att-ed-row" + (mrow.suppressed ? " off" : "")} key={mrow.event_id}>
                <span class="att-ed-time">{mrow.time}</span>
                {mrow.suppressed && <span class="att-ed-badge">đã ẩn</span>}
                {canEdit && <button class="btn att-ed-btn" disabled={busy}
                  onClick={() => run(() => suppressAttendance(mrow.event_id, !mrow.suppressed),
                    mrow.suppressed ? `Đã hiện lại giờ ${mrow.time}` : `Đã ẩn giờ ${mrow.time}`)}>
                  {mrow.suppressed ? "Hiện lại" : "Ẩn"}
                </button>}
              </div>
            ))}
            <div class="att-ed-sec">Giờ thêm tay</div>
            {det.manual.map((mn) => (
              <div class="att-ed-row" key={mn.id}>
                <span class="att-ed-time">{mn.time}</span>
                <span class="muted small">✎ {mn.created_by || "?"}</span>
                {canEdit && <button class="btn att-ed-btn danger" disabled={busy}
                  onClick={async () => { if (await confirmDialog(`Xoá giờ thêm tay ${mn.time}?`, { danger: true, okLabel: "Xoá" })) run(() => deleteAttendanceManual(mn.id), `Đã xoá giờ ${mn.time}`); }}>Xoá</button>}
              </div>
            ))}
            {canEdit && <>
              <div class="att-ed-row att-ed-add">
                <input type="time" class="pw-input" value={newTime} disabled={busy}
                  onInput={(e: any) => setNewTime(e.target.value)} />
                <button class="btn att-ed-btn" disabled={busy || !newTime} onClick={addTime}>＋ Thêm giờ</button>
              </div>
              <div class="muted small att-ed-note">
                Giờ máy không sửa trực tiếp được — muốn sửa 1 giờ: bấm <b>Ẩn</b> giờ sai rồi
                <b> Thêm giờ</b> đúng. Dữ liệu máy giữ nguyên nên lần đồng bộ sau không đè phần sửa.
              </div>
            </>}
          </>
        )}
      </div>
    </div>
  );
}
