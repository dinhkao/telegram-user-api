// Cảnh báo GHI CHÚ không trùng khít câu chuẩn, trong báo cáo thợ (dashboard SX #/sx-bang).
// Phụ cấp tự động khớp ghi chú theo TỪ KHOÁ cài sẵn; ghi chú lệch một chữ là auto hoặc
// trả sai hoặc không trả gì, mà không báo. Khối này gom theo cặp (thợ, ghi chú) để văn
// phòng soi, tick ✓ là dòng đó biến khỏi danh sách (production_note_resolved).
// CHỈ VĂN PHÒNG (kèm số tiền phụ cấp); server cũng chặn 403.
// API: getProductionNoteReview / resolveNoteReview → server_app/production_dashboard_routes.py.
import { useEffect, useState } from "preact/hooks";
import { getProductionNoteReview, resolveNoteReview, type NoteReviewGroup, type NoteReviewRow } from "../api";
import { moneyD } from "../format";
import { toast } from "../ui/feedback";
import { ErrorState, LoadingInline } from "../ui/states";

const dmy = (ymd?: string | null) => (ymd ? ymd.split("-").reverse().slice(0, 2).join("/") : "—");

type Rng = { from?: string; to?: string };

function Group({ g, rng, onDone }: { g: NoteReviewGroup; rng: Rng; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  // Tick ở dòng NHÓM = xử lý mọi lần ghi như vậy của thợ đó trong khoảng đang xem;
  // tick ở dòng con = đúng 1 phiếu. Cả hai gọi chung 1 endpoint.
  async function resolve(row?: NoteReviewRow) {
    if (busy) return;
    setBusy(true);
    try {
      const r = await resolveNoteReview({
        worker: g.worker, note: g.note, ...rng,
        ...(row ? { thread_id: row.thread_id, worker_raw: row.worker_raw } : {}),
      });
      toast(`Đã đánh dấu xử lý ${r.n} dòng`, "ok");
      onDone();
    } catch (e: any) {
      toast(e?.message || "Lỗi đánh dấu", "err");
      setBusy(false);
    }
  }

  return (
    <div class="nra-g">
      <div class="nra-row">
        <button
          class="nra-tick" disabled={busy} aria-label="Đánh dấu đã xử lý cả nhóm"
          title={g.count > 1 ? `Đánh dấu đã xử lý ${g.count} dòng` : "Đánh dấu đã xử lý"}
          onClick={() => resolve()}
        >☐</button>
        <button class="nra-main" onClick={() => setOpen(!open)}>
          <span class="nra-w">{g.worker}</span>
          <span class="nra-note">“{g.note}”</span>
          <span class="nra-n">
            {g.count > 1 ? `${g.count} lần · ` : ""}{dmy(g.last_ymd)} {open ? "▾" : "▸"}
          </span>
        </button>
      </div>
      {open && g.rows.map((r) => (
        <div key={r.thread_id} class="nra-sub">
          <button class="nra-tick" disabled={busy} title="Đánh dấu đã xử lý phiếu này"
                  aria-label="Đánh dấu đã xử lý" onClick={() => resolve(r)}>☐</button>
          <a class="nra-sub-link" href={`#/san_xuat/${r.thread_id}`}>
            <span>{dmy(r.ymd)} · {r.product_code}</span>
            <span class={r.allowance > 0 ? "t-ok" : "muted"}>
              {r.allowance > 0 ? `${moneyD(r.allowance)}${r.allow_by === "auto" ? " (auto)" : ""}` : "chưa có phụ cấp"}
            </span>
          </a>
        </div>
      ))}
      {open && g.count > g.rows.length && <span class="nra-more muted small">… và {g.count - g.rows.length} lần nữa</span>}
    </div>
  );
}

const SECTIONS: { kind: NoteReviewGroup["kind"]; head: string; danger?: boolean }[] = [
  { kind: "so_tien", head: "Có ghi SỐ TIỀN — auto trả ĐÚNG số này, không theo hạng" },
  { kind: "mot_phan", head: "Đúng từ khoá nhưng THỪA CHỮ — auto vẫn trả tiền, bỏ qua phần thừa", danger: true },
  { kind: "la", head: "Chữ lạ — chưa có trong bảng từ khoá" },
  { kind: "khac_tho", head: "Từ khoá của thợ khác — thợ này chưa có luật cho việc đó" },
  { kind: "so_luong", head: "Chỉ chỉnh số lượng / giờ — không phải tên việc" },
];

export function ProductionNoteAlerts({ from, to }: Rng) {
  const [data, setData] = useState<{ groups: NoteReviewGroup[]; resolved: number } | null>(null);
  const [err, setErr] = useState("");
  // `tick` để nút Thử lại + tick ✓ nạp lại được: effect chỉ chạy theo [from, to] nên khi
  // API lỗi khối này sẽ đứng im vĩnh viễn, người dùng tưởng "không có cảnh báo nào".
  const [tick, setTick] = useState(0);
  const reload = () => setTick((n) => n + 1);
  useEffect(() => {
    let alive = true;
    setErr("");
    setData(null);
    getProductionNoteReview(from, to)
      .then((d) => { if (alive) { setData({ groups: d.groups, resolved: d.resolved || 0 }); setErr(""); } })
      .catch((e: any) => { if (alive) { setData({ groups: [], resolved: 0 }); setErr(e?.message || "Lỗi tải"); } });
    return () => { alive = false; };
  }, [from, to, tick]);

  if (err) {
    return (
      <section class="card nra">
        <label class="card-label t-warn">⚠️ Ghi chú cần xem lại phụ cấp</label>
        <ErrorState msg={`Không tải được: ${err}`} onRetry={reload} />
      </section>
    );
  }
  if (data === null) return <section class="card"><LoadingInline /></section>;
  if (!data.groups.length) {
    // Đã tick hết = tin tốt, nói ra; chưa có cảnh báo nào thì im lặng cho gọn trang.
    return data.resolved > 0 ? (
      <section class="card nra">
        <label class="card-label t-ok">✓ Đã xử lý hết ghi chú cần xem lại ({data.resolved} dòng)</label>
      </section>
    ) : null;
  }

  const rng: Rng = { from, to };
  return (
    <section class="card nra">
      <label class="card-label t-warn">⚠️ Ghi chú cần xem lại phụ cấp ({data.groups.length})</label>
      {SECTIONS.map(({ kind, head, danger }) => {
        const gs = data.groups.filter((g) => g.kind === kind);
        if (!gs.length) return null;
        return (
          <>
            <p class={danger ? "nra-hd t-danger" : "nra-hd"}>{head}</p>
            {gs.map((g) => <Group key={g.worker + g.note} g={g} rng={rng} onDone={reload} />)}
          </>
        );
      })}
      <p class="muted small nra-foot">
        Ghi chú phải TRÙNG KHÍT một câu đã cài cho đúng thợ đó thì phụ cấp tự động mới
        chạy đúng ý. Dòng “chữ lạ” / “thợ khác” KHÔNG được tính tự động — nếu đúng là
        việc có phụ cấp thì nhập tay trong phiếu. Dòng “thừa chữ” thì auto VẪN trả
        nhưng ghi số theo hạng và bỏ qua phần viết thêm — đối chiếu rồi sửa tay nếu lệch.
        Xem xong bấm ☐ để dòng đó khỏi hiện lại{data.resolved > 0 ? ` (đã xử lý ${data.resolved} dòng)` : ""}.
      </p>
    </section>
  );
}
