// Chi tiết 1 thùng (#/thung/:id) — info hub: mã, số cây, tình trạng, ai nhập, ngày,
// thuộc phiếu SX nào (link), đã xuất đơn nào (link → cuộn+nháy thùng trong đơn).
// GET /api/inventory/box/:id.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { boxDetail, updateBox, setBoxDisabled, listPlaces, createPlace, setBoxPlace, soVN, type InvBoxDetail, type InvBox, type Place } from "../api";
import { onRealtime } from "../realtime";
import { Loading } from "../ui/states";
import { confirmDialog } from "../ui/feedback";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { Icon } from "../ui/Icon";

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
  const [places, setPlaces] = useState<Place[]>([]);
  const [newPlace, setNewPlace] = useState<string | null>(null);   // đang tạo vị trí mới
  useEffect(() => { listPlaces().then(setPlaces).catch(() => {}); }, []);

  const pickPlace = async (val: string) => {
    if (val === "__new") { setNewPlace(""); return; }
    try {
      const b = await setBoxPlace(boxId, val ? Number(val) : null);
      if (b && d) setD({ ...d, box: b });
    } catch { /* im */ }
  };
  const saveNewPlace = async () => {
    const name = (newPlace || "").trim();
    if (!name) { setNewPlace(null); return; }
    try {
      const p = await createPlace(name);
      setPlaces((prev) => (prev.some((x) => x.id === p.id) ? prev : [...prev, p]));
      const b = await setBoxPlace(boxId, p.id);
      if (b && d) setD({ ...d, box: b });
    } catch { /* im */ }
    setNewPlace(null);
  };

  const reload = (showLoading: boolean) => {
    if (showLoading) setLoading(true);
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
  };

  useEffect(() => {
    reload(true);
  }, [boxId]);

  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const rel = e.type === "resync" || e.type === "inventory_changed" || e.type === "production_changed" ||
        e.type === "order_changed" ||   // xuất/thu hồi cho đơn đổi phần còn lại
        (e.type === "box_changed" && (e.box_id == null || e.box_id === String(boxId)));
      if (rel) {
        clearTimeout(t);
        t = setTimeout(() => reload(false), 300);
      }
    });
    return () => { off(); clearTimeout(t); };
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
    } else if (!(await confirmDialog(`Kích hoạt lại thùng ${d.box.box_code}? Thùng sẽ tính lại vào tồn kho + phiếu SX.`))) {
      return; // huỷ kích hoạt lại
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

  if (loading) return <Loading />;
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
        <BackLink fallback={`#/kho/${encodeURIComponent(backCode)}`} />
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
          <span class="box-k">Vị trí</span>
          {newPlace === null ? (
            <select class="box-place" value={b.place_id ?? ""} onChange={(e: any) => pickPlace(e.target.value)}>
              <option value="">— Chưa xếp —</option>
              {places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              <option value="__new">➕ Tạo vị trí mới…</option>
            </select>
          ) : (
            <span class="row" style={{ gap: "6px" }}>
              <input class="box-place" autofocus placeholder="Tên vị trí (vd Kho A)" value={newPlace}
                onInput={(e: any) => setNewPlace(e.target.value)}
                onKeyDown={(e: any) => { if (e.key === "Enter") saveNewPlace(); if (e.key === "Escape") setNewPlace(null); }} />
              <button class="btn small primary" onClick={saveNewPlace}>Lưu</button>
              <button class="btn small" onClick={() => setNewPlace(null)}>✕</button>
            </span>
          )}
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
            <Icon name="factory" size={16} /> {d.source_slip.sp_name || b.product_code}
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
                  <Icon name="clipboard" size={16} /> Đơn #{a.order_thread_id} · lấy {soVN(a.quantity)}
                  {a.allocated_by ? ` · ${a.allocated_by}` : ""} →
                </a>
                {a.order_text ? <div class="box-alloc-peek">{a.order_text}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Images base={`/api/media/box/${b.id}`} />
      <Comments base={`/api/media/box/${b.id}`} />
      <History base={`/api/media/box/${b.id}`} />

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
                {disBusy ? "…" : disabled ? <><Icon name="check" size={16} /> Kích hoạt lại thùng</> : <><Icon name="ban" size={16} /> Vô hiệu hoá thùng</>}
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
