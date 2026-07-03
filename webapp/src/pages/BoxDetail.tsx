// Chi tiết 1 thùng (#/thung/:id) — info hub: mã, số cây, tình trạng, ai nhập, ngày,
// thuộc phiếu SX nào (link), đã xuất đơn nào (link → cuộn+nháy thùng trong đơn).
// GET /api/inventory/box/:id.
import { useEffect, useState } from "preact/hooks";
import { boxDetail, updateBox, soVN, type InvBoxDetail } from "../api";

const STATUS: Record<string, { label: string; cls: string }> = {
  in_stock: { label: "Trong kho", cls: "in" },
  allocated: { label: "Đã xuất đơn", cls: "alloc" },
  shipped: { label: "Đã giao", cls: "ship" },
};

function fmtWhen(iso?: string | null): string {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return iso;
  const [, y, mo, d, hh, mi] = m;
  return `${d}/${mo}/${y} ${hh}:${mi}`;
}

export function BoxDetail({ boxId }: { boxId: string }) {
  const [d, setD] = useState<InvBoxDetail | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [noteInput, setNoteInput] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);

  useEffect(() => {
    setLoading(true);
    boxDetail(boxId)
      .then((r) => {
        if (!r) setErr("Không tìm thấy thùng");
        else {
          setD(r);
          setNoteInput(r.box.note || "");
        }
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải thùng"))
      .finally(() => setLoading(false));
  }, [boxId]);

  const saveNote = async () => {
    if (!d || noteInput === (d.box.note || "")) return;
    try {
      const b = await updateBox(boxId, { note: noteInput.trim() });
      if (b) {
        setD({ ...d, box: b });
        setNoteSaved(true);
        setTimeout(() => setNoteSaved(false), 1500);
      }
    } catch (e: any) {
      setErr(e?.message || "Lỗi lưu ghi chú");
    }
  };

  if (loading) return <div class="muted">Đang tải…</div>;
  if (err || !d)
    return (
      <div class="muted">
        {err || "Không tìm thấy thùng"}. <a href="#/kho">← Kho</a>
      </div>
    );

  const b = d.box;
  const st = STATUS[b.status] || { label: b.status, cls: "" };
  const backCode = b.product_code;

  return (
    <div class="box-detail">
      <div class="prod-detail-head">
        <a class="back" href={`#/kho/${encodeURIComponent(backCode)}`}>
          ←
        </a>
        <div>
          <div class="prod-sp big">
            <code>{b.box_code}</code>
          </div>
          <div class="prod-date muted">
            {b.product_code} · <span class={`inv-status ${st.cls}`}>{st.label}</span>
          </div>
        </div>
      </div>

      <section class="card">
        <div class="box-kv">
          <span class="box-k">Số cây</span>
          <span class="box-v big">{soVN(b.quantity)}</span>
        </div>
        <div class="box-kv">
          <span class="box-k">Người nhập</span>
          <span class="box-v">{b.created_by || "—"}</span>
        </div>
        <div class="box-kv">
          <span class="box-k">Ngày nhập</span>
          <span class="box-v">{fmtWhen(b.created_at)}</span>
        </div>
      </section>

      <section class="card">
        <label class="card-label">Ghi chú {noteSaved && <span class="muted small">✓ đã lưu</span>}</label>
        <textarea
          rows={2}
          value={noteInput}
          onInput={(e) => setNoteInput((e.target as HTMLTextAreaElement).value)}
          onBlur={saveNote}
          placeholder="Ghi chú cho thùng (tự lưu khi rời ô)…"
        />
      </section>

      <section class="card">
        <label class="card-label">Nguồn — Phiếu sản xuất</label>
        {d.source_slip ? (
          <a class="box-jump" href={`#/san_xuat/${d.source_slip.thread_id}?focus=box:${b.id}`}>
            🏭 {d.source_slip.sp_name || b.product_code}
            {d.source_slip.date ? ` · ${d.source_slip.date}` : ""} →
          </a>
        ) : (
          <div class="muted small">Không rõ phiếu nguồn.</div>
        )}
      </section>

      <section class="card">
        <label class="card-label">Phân bổ — Đơn hàng</label>
        {b.status === "allocated" && b.order_thread_id ? (
          <a class="box-jump" href={`#/order/${b.order_thread_id}?focus=box:${b.id}`}>
            📋 Đơn #{b.order_thread_id}
            {b.allocated_by ? ` · ${b.allocated_by}` : ""} →
          </a>
        ) : b.status === "shipped" && b.order_thread_id ? (
          <a class="box-jump" href={`#/order/${b.order_thread_id}?focus=box:${b.id}`}>
            📋 Đơn #{b.order_thread_id} (đã giao) →
          </a>
        ) : (
          <div class="muted small">Chưa phân bổ vào đơn nào — còn trong kho.</div>
        )}
      </section>
    </div>
  );
}
