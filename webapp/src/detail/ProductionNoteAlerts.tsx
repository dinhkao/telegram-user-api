// Cảnh báo GHI CHÚ LẠ trong báo cáo thợ (dùng ở dashboard sản xuất #/sx-bang).
// Phụ cấp tự động khớp ghi chú theo TỪ KHOÁ cài sẵn — thợ ghi chữ khác thì auto không
// ghi phụ cấp mà cũng không báo gì. Khối này liệt kê các cặp (thợ, ghi chú) không khớp
// để văn phòng xem lại. CHỈ VĂN PHÒNG (kèm số tiền phụ cấp); server cũng chặn 403.
// API: getProductionNoteReview → server_app/production_dashboard_routes.py.
import { useEffect, useState } from "preact/hooks";
import { getProductionNoteReview, type NoteReviewGroup } from "../api";
import { moneyD } from "../format";
import { ErrorState, LoadingInline } from "../ui/states";

const dmy = (ymd?: string | null) => (ymd ? ymd.split("-").reverse().slice(0, 2).join("/") : "—");

function Group({ g }: { g: NoteReviewGroup }) {
  const [open, setOpen] = useState(false);
  return (
    <div class="nra-g">
      <button class="nra-row" onClick={() => setOpen(!open)}>
        <span class="nra-w">{g.worker}</span>
        <span class="nra-note">“{g.note}”</span>
        <span class="nra-n">
          {g.count > 1 ? `${g.count} lần · ` : ""}{dmy(g.last_ymd)} {open ? "▾" : "▸"}
        </span>
      </button>
      {open && g.rows.map((r) => (
        <a key={r.thread_id} class="nra-sub" href={`#/san_xuat/${r.thread_id}`}>
          <span>{dmy(r.ymd)} · {r.product_code}</span>
          <span class={r.allowance > 0 ? "t-ok" : "muted"}>
            {r.allowance > 0 ? `${moneyD(r.allowance)}${r.allow_by === "auto" ? " (auto)" : ""}` : "chưa có phụ cấp"}
          </span>
        </a>
      ))}
      {open && g.count > g.rows.length && <span class="nra-more muted small">… và {g.count - g.rows.length} lần nữa</span>}
    </div>
  );
}

export function ProductionNoteAlerts({ from, to }: { from?: string; to?: string }) {
  const [groups, setGroups] = useState<NoteReviewGroup[] | null>(null);
  const [err, setErr] = useState("");
  // `tick` để nút Thử lại nạp lại được: effect chỉ chạy theo [from, to] nên khi API
  // lỗi (vd route chưa có trong tiến trình đang chạy) khối này đứng im vĩnh viễn —
  // người dùng tưởng "không có cảnh báo nào" thay vì "chưa tải được".
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setErr("");
    setGroups(null);
    getProductionNoteReview(from, to)
      .then((d) => { if (alive) { setGroups(d.groups); setErr(""); } })
      .catch((e: any) => { if (alive) { setGroups([]); setErr(e?.message || "Lỗi tải"); } });
    return () => { alive = false; };
  }, [from, to, tick]);

  if (err) {
    return (
      <section class="card nra">
        <label class="card-label t-warn">⚠️ Ghi chú cần xem lại phụ cấp</label>
        <ErrorState msg={`Không tải được: ${err}`} onRetry={() => setTick((n) => n + 1)} />
      </section>
    );
  }
  if (groups === null) return <section class="card"><LoadingInline /></section>;
  if (!groups.length) return null;

  const tien = groups.filter((g) => g.kind === "so_tien");
  const phan = groups.filter((g) => g.kind === "mot_phan");
  const la = groups.filter((g) => g.kind === "la");
  const khac = groups.filter((g) => g.kind === "khac_tho");
  const sl = groups.filter((g) => g.kind === "so_luong");
  return (
    <section class="card nra">
      <label class="card-label t-warn">⚠️ Ghi chú cần xem lại phụ cấp ({groups.length})</label>
      {tien.length > 0 && (
        <>
          <p class="nra-hd">Có ghi SỐ TIỀN — auto trả ĐÚNG số này, không theo hạng</p>
          {tien.map((g) => <Group key={g.worker + g.note} g={g} />)}
        </>
      )}
      {phan.length > 0 && (
        <>
          <p class="nra-hd t-danger">Đúng từ khoá nhưng THỪA CHỮ — auto vẫn trả tiền, bỏ qua phần thừa</p>
          {phan.map((g) => <Group key={g.worker + g.note} g={g} />)}
        </>
      )}
      {la.length > 0 && (
        <>
          <p class="nra-hd">Chữ lạ — chưa có trong bảng từ khoá</p>
          {la.map((g) => <Group key={g.worker + g.note} g={g} />)}
        </>
      )}
      {khac.length > 0 && (
        <>
          <p class="nra-hd">Từ khoá của thợ khác — thợ này chưa có luật cho việc đó</p>
          {khac.map((g) => <Group key={g.worker + g.note} g={g} />)}
        </>
      )}
      {sl.length > 0 && (
        <>
          <p class="nra-hd">Chỉ chỉnh số lượng / giờ — không phải tên việc</p>
          {sl.map((g) => <Group key={g.worker + g.note} g={g} />)}
        </>
      )}
      <p class="muted small nra-foot">
        Ghi chú phải TRÙNG KHÍT một câu đã cài cho đúng thợ đó thì phụ cấp tự động mới
        chạy đúng ý. Dòng “chữ lạ” / “thợ khác” KHÔNG được tính tự động — nếu đúng là
        việc có phụ cấp thì nhập tay trong phiếu. Dòng “thừa chữ” thì auto VẪN trả
        nhưng ghi số theo hạng và bỏ qua phần viết thêm — đối chiếu rồi sửa tay nếu lệch.
      </p>
    </section>
  );
}
