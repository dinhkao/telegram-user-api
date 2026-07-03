// Chi tiết 1 thùng (#/thung/:id) — info hub: mã, số cây, tình trạng, ai nhập, ngày,
// thuộc phiếu SX nào (link), đã xuất đơn nào (link → cuộn+nháy thùng trong đơn).
// GET /api/inventory/box/:id.
import { useEffect, useState } from "preact/hooks";
import { boxDetail, updateBox, setBoxDisabled, soVN, type InvBoxDetail, type InvBox } from "../api";

const isDisabled = (b: InvBox) => !!b.disabled;

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
  const [mfgInput, setMfgInput] = useState("");
  const [disBusy, setDisBusy] = useState(false);

  useEffect(() => {
    setLoading(true);
    boxDetail(boxId)
      .then((r) => {
        if (!r) setErr("Không tìm thấy thùng");
        else {
          setD(r);
          setNoteInput(r.box.note || "");
          setMfgInput(r.box.mfg_date || "");
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

  const saveMfg = async (v: string) => {
    if (!d || v === (d.box.mfg_date || "")) return;
    try {
      const b = await updateBox(boxId, { mfg_date: v });
      if (b) setD({ ...d, box: b });
    } catch (e: any) {
      setErr(e?.message || "Lỗi lưu ngày SX");
    }
  };

  const toggleDisabled = async () => {
    if (!d) return;
    const next = !isDisabled(d.box);
    let reason = "";
    if (next) {
      reason = (prompt("Lý do vô hiệu thùng này?") || "").trim();
      if (!reason) return; // huỷ hoặc bỏ trống → không làm gì
    }
    setDisBusy(true);
    setErr("");
    try {
      const b2 = await setBoxDisabled(boxId, next, reason);
      if (b2) setD({ ...d, box: b2 });
    } catch (e: any) {
      setErr(e?.message || "Lỗi cập nhật");
    } finally {
      setDisBusy(false);
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
  const backCode = b.product_code;
  const used = b.allocated ?? 0;
  const remaining = b.remaining ?? b.quantity;
  const disabled = isDisabled(b);

  return (
    <div class={disabled ? "box-detail is-disabled" : "box-detail"}>
      <div class="prod-detail-head">
        <a class="back" href={`#/kho/${encodeURIComponent(backCode)}`}>
          ←
        </a>
        <div>
          <div class="prod-sp big">
            <code>{b.box_code}</code>
          </div>
          <div class="prod-date muted">
            {b.product_code}
            {disabled && <span class="inv-status disabled"> Vô hiệu</span>}
          </div>
        </div>
      </div>

      {disabled && (
        <div class="box-disabled-banner">
          🚫 Thùng đã bị vô hiệu — không tính tồn kho, không phân bổ đơn, không tính vào phiếu SX.
          {b.disabled_reason ? (
            <div class="box-disabled-reason">Lý do: {b.disabled_reason}</div>
          ) : null}
        </div>
      )}

      <section class="card">
        <div class="box-kv">
          <span class="box-k">Số cây</span>
          <span class="box-v big">{soVN(b.quantity)}</span>
        </div>
        <div class="box-kv">
          <span class="box-k">Còn lại</span>
          <span class="box-v big" style={{ color: remaining > 0 ? "#2b6b2b" : "#a15c00" }}>
            {soVN(remaining)}
          </span>
          {used > 0 ? <span class="muted small">đã xuất {soVN(used)}</span> : null}
        </div>
        <div class="box-kv">
          <span class="box-k">Ngày SX</span>
          <input
            class="box-mfg"
            type="date"
            value={mfgInput}
            onInput={(e) => setMfgInput((e.target as HTMLInputElement).value)}
            onChange={(e) => saveMfg((e.target as HTMLInputElement).value)}
          />
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
        <label class="card-label">Đã xuất cho đơn</label>
        {d.allocations.length === 0 ? (
          <div class="muted small">Chưa xuất cho đơn nào — còn trong kho.</div>
        ) : (
          <ul class="box-alloc-list">
            {d.allocations.map((a) => (
              <li key={a.allocation_id}>
                <a class="box-jump" href={`#/order/${a.order_thread_id}?focus=box:${b.id}`}>
                  📋 Đơn #{a.order_thread_id} · lấy {soVN(a.quantity)}
                  {a.allocated_by ? ` · ${a.allocated_by}` : ""} →
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section class="card">
        {(() => {
          const blocked = !disabled && d.allocations.length > 0; // đã xuất đơn → cấm vô hiệu
          return (
            <>
              <button
                class={disabled ? "btn block" : "btn danger block"}
                disabled={disBusy || blocked}
                onClick={toggleDisabled}
              >
                {disBusy ? "…" : disabled ? "✅ Kích hoạt lại thùng" : "🚫 Vô hiệu hoá thùng"}
              </button>
              {blocked && (
                <div class="muted small">Thùng đã phân bổ vào đơn — thu hồi khỏi đơn trước khi vô hiệu.</div>
              )}
            </>
          );
        })()}
      </section>
    </div>
  );
}
