// Chi tiết 1 thùng (#/thung/:id) — info hub: mã, số cây, tình trạng, ai nhập, ngày,
// thuộc phiếu SX nào (link), đã xuất đơn nào (link → cuộn+nháy thùng trong đơn).
// GET /api/inventory/box/:id.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { boxDetail, updateBox, setBoxDisabled, deleteBox, listPlaces, createPlace, setBoxPlace, listUnits, createUnit, setBoxUnit, currentUser, soVN, type InvBoxDetail, type InvBox, type Place, type Unit } from "../api";
import { onRealtime } from "../realtime";
import { Loading } from "../ui/states";
import { confirmDialog, toast } from "../ui/feedback";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { Icon } from "../ui/Icon";
import { SelectPopup } from "../ui/SelectPopup";

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
  useEffect(() => { listPlaces().then(setPlaces).catch(() => {}); }, []);
  const [units, setUnits] = useState<Unit[]>([]);
  useEffect(() => { listUnits().then(setUnits).catch(() => {}); }, []);

  const pickUnit = async (val: string) => {
    if (!val) return;
    try { const b = await setBoxUnit(boxId, Number(val)); if (b && d) setD({ ...d, box: b }); } catch { /* im */ }
  };
  const createUnitAssign = async (name: string) => {
    try {
      const u = await createUnit(name);
      setUnits((prev) => (prev.some((x) => x.id === u.id) ? prev : [...prev, u]));
      const b = await setBoxUnit(boxId, u.id);
      if (b && d) setD({ ...d, box: b });
    } catch { /* im */ }
  };
  // CHUYỂN KHO — hành động rõ ràng (không phải "sửa field"): nút mở popup chọn
  // kho đích → chuyển → toast "001: Kho A → Kho B". Ghi lịch sử thao tác (audit).
  const [movePop, setMovePop] = useState(false);
  const doMove = async (val: string) => {
    if (!d) return;
    const from = d.box.place_name || "Chưa xếp";
    if (String(d.box.place_id ?? "") === val) { toast(`Thùng đang ở ${from} rồi`, "info"); return; }
    try {
      const b = await setBoxPlace(boxId, val ? Number(val) : null);
      if (b) {
        setD({ ...d, box: b });
        toast(`Đã chuyển thùng ${b.box_code}: ${from} → ${b.place_name || "Chưa xếp"}`, "ok");
      }
    } catch (e: any) { toast(e?.message || "Lỗi chuyển kho", "err"); }
  };
  const createPlaceAssign = async (name: string) => {
    try {
      const p = await createPlace(name);
      setPlaces((prev) => (prev.some((x) => x.id === p.id) ? prev : [...prev, p]));
      await doMove(String(p.id));
    } catch { /* im */ }
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

  const isAdmin = currentUser()?.role === "admin";
  const doDelete = async () => {
    if (!d) return;
    // Đã xuất/tiêu hao → nút mờ, bấm chỉ toast lý do (server cũng chặn)
    if (d.allocations.length > 0) {
      toast("Thùng đã xuất cho đơn — thu hồi trước khi xoá", "info"); return;
    }
    if (!(await confirmDialog(`Xoá HẲN thùng ${d.box.box_code}? Không thể hoàn tác.`, { danger: true, okLabel: "Xoá" }))) return;
    setDisBusy(true); setErr("");
    try {
      await deleteBox(boxId);
      const code = d.box.product_code;
      window.location.hash = `#/kho/${encodeURIComponent(code)}`;
    } catch (e: any) {
      setErr(e?.message || "Lỗi xoá thùng");
      setDisBusy(false);
    }
  };

  // Tính năng VÔ HIỆU thùng đã TẮT (hàng chỉ 2 đường: nhập phiếu SX / xuất đơn).
  // Chỉ còn KÍCH HOẠT LẠI cho thùng đã vô hiệu từ trước (server chặn chiều vô hiệu).
  const reactivate = async () => {
    if (!d) return;
    if (!(await confirmDialog(`Kích hoạt lại thùng ${d.box.box_code}? Thùng sẽ tính lại vào tồn kho + phiếu SX.`))) return;
    setDisBusy(true);
    setErr("");
    try {
      const b2 = await setBoxDisabled(boxId, false, "");
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
          <span class="box-k">Số {b.product_unit || "cây"}</span>
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
          <span class="box-k">Đơn vị</span>
          <SelectPopup title="Đơn vị chứa" placeholder="Thùng (mặc định)" searchable onCreate={createUnitAssign}
            value={b.unit_id ?? ""} options={units.map((u) => ({ value: u.id, label: u.name }))}
            onChange={pickUnit} />
        </div>
        <div class="box-kv">
          <span class="box-k">Vị trí</span>
          <span class={"box-v box-place" + (b.place_name ? "" : " muted")}>
            <Icon name="tag" size={14} /> {b.place_name || "Chưa xếp"}
          </span>
          <button class="btn small box-move-btn" onClick={() => setMovePop(true)}>
            <Icon name="truck" size={14} /> Chuyển kho
          </button>
        </div>
        <SelectPopup open={movePop} onClose={() => setMovePop(false)}
          title={`Chuyển thùng ${b.box_code} tới…`} searchable onCreate={createPlaceAssign}
          value={b.place_id ?? ""}
          options={[{ value: "", label: "— Chưa xếp —" }, ...places.map((p) => ({ value: p.id, label: p.name }))]}
          onChange={doMove} />
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
        <label class="card-label">Đã xuất / tiêu hao</label>
        {d.allocations.length === 0 ? (
          <div class="muted small">Chưa xuất cho đơn nào — còn trong kho.</div>
        ) : (
          <ul class="box-alloc-list">
            {d.allocations.map((a) => {
              const prod = (a as any).kind === "production";
              return (
                <li key={a.allocation_id}>
                  <a class="box-jump" href={`${prod ? "#/san_xuat" : "#/order"}/${a.order_thread_id}?focus=box:${b.id}`}>
                    <Icon name={prod ? "factory" : "clipboard"} size={16} />{" "}
                    {prod ? "Phiếu SX" : "Đơn"} #{a.order_thread_id} · {prod ? "tiêu hao" : "lấy"} {soVN(a.quantity)}
                    {a.allocated_by ? ` · ${a.allocated_by}` : ""} →
                  </a>
                  {a.order_text ? <div class="box-alloc-peek">{a.order_text}</div> : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <Images base={`/api/media/box/${b.id}`} />
      <Comments base={`/api/media/box/${b.id}`} />
      <History base={`/api/media/box/${b.id}`} />

      {/* Vô hiệu thùng đã TẮT — chỉ còn kích hoạt lại thùng vô hiệu từ trước */}
      {disabled && (
        <section class="card">
          <button class="btn block" disabled={disBusy} onClick={reactivate}>
            {disBusy ? "…" : <><Icon name="check" size={16} /> Kích hoạt lại thùng</>}
          </button>
        </section>
      )}

      {isAdmin && (
        <section class="card">
          <button class={"btn danger block" + (d.allocations.length > 0 ? " faded" : "")} disabled={disBusy} onClick={doDelete}
            title={d.allocations.length > 0 ? "Đã xuất cho đơn — thu hồi trước khi xoá" : undefined}>
            <Icon name="trash" size={16} /> Xoá thùng (admin)
          </button>
          {d.allocations.length > 0 && <div class="muted small">Đã xuất cho đơn — thu hồi trước khi xoá.</div>}
        </section>
      )}
    </div>
  );
}
