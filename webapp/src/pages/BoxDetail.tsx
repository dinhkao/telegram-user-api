// Chi tiết 1 thùng (#/thung/:id) — info hub: mã, số cây, tình trạng, ai nhập, ngày,
// thuộc phiếu SX nào (link), đã xuất đơn nào (link → cuộn+nháy thùng trong đơn).
// GET /api/inventory/box/:id.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { boxDetail, updateBox, setBoxDisabled, deleteBox, transferBox, allBoxes, listPlaces, createPlace, setBoxPlace, listUnits, createUnit, setBoxUnit, currentUser, soVN, type InvBoxDetail, type InvBox, type KhoBox, type Place, type Unit } from "../api";
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
    // Đã xuất/tiêu hao/chuyển → nút mờ, bấm chỉ toast lý do (server cũng chặn)
    if (d.allocations.length > 0) {
      toast("Thùng có lịch sử xuất/chuyển — không xoá được", "info"); return;
    }
    // Thùng ĐÓNG GÓI từ nguyên liệu → nói rõ xoá sẽ hoàn NL gì, bao nhiêu
    const packed = d.packed_materials || [];
    const cfMsg = packed.length
      ? `Thùng ${d.box.box_code} được đóng gói từ: ${packed.map((p) => `${soVN(p.amount)} ${p.code}`).join(", ")}.\n`
        + `Xoá thùng sẽ HOÀN TRẢ số nguyên liệu này về kho.\nXoá thùng ${d.box.box_code}?`
      : `Xoá HẲN thùng ${d.box.box_code}? Không thể hoàn tác.`;
    if (!(await confirmDialog(cfMsg, { danger: true, okLabel: "Xoá" }))) return;
    setDisBusy(true); setErr("");
    try {
      const r = await deleteBox(boxId);
      // Báo rõ NL hoàn về THÙNG NÀO (mã gọi + id) để ngoài kho tìm đúng thùng
      const rest: { code: string; amount: number; boxes?: { box_id: number; box_code: string; amount: number }[] }[]
        = r?.restored_materials || [];
      if (rest.length) {
        const lines = rest.flatMap((m) => (m.boxes || []).map(
          (bx) => `• ${soVN(bx.amount)} ${m.code} → thùng ${bx.box_code} (id ${bx.box_id})`));
        await confirmDialog(`✅ Đã hoàn nguyên liệu về kho:\n${lines.join("\n")}`, { okLabel: "OK", cancelLabel: "Đóng" });
      }
      const code = d.box.product_code;
      window.location.hash = `#/kho/${encodeURIComponent(code)}`;
    } catch (e: any) {
      setErr(e?.message || "Lỗi xoá thùng");
      setDisBusy(false);
    }
  };

  // Chuyển hàng sang thùng khác cùng SP
  const [xferTargets, setXferTargets] = useState<KhoBox[]>([]);
  const [xferTo, setXferTo] = useState<number | null>(null);
  const [xferQty, setXferQty] = useState("");
  const [xferBusy, setXferBusy] = useState(false);
  useEffect(() => {
    if (!d) return;
    allBoxes().then((bs) => setXferTargets(
      bs.filter((x) => x.product_code === d.box.product_code && x.id !== d.box.id && !x.disabled),
    )).catch(() => {});
  }, [d?.box?.id, d?.box?.product_code]);
  const doTransfer = async () => {
    if (!d) return;
    const q = parseFloat((xferQty || "").replace(",", "."));
    const rem = d.box.remaining ?? d.box.quantity;
    if (!xferTo) { toast("Chọn thùng đích", "err"); return; }
    if (!isFinite(q) || q <= 0) { toast("Số lượng phải > 0", "err"); return; }
    if (q > rem) { toast(`Thùng chỉ còn ${soVN(rem)}`, "err"); return; }
    const tgt = xferTargets.find((x) => x.id === xferTo);
    const uThis = (d.box.unit_name || "thùng").toLowerCase();
    const uTgt = (tgt?.unit_name || "thùng").toLowerCase();
    const pu = d.box.product_unit || "cây";
    if (!(await confirmDialog(`Chuyển ${soVN(q)} ${pu} ${d.box.product_code} từ ${uThis} ${d.box.box_code} → ${uTgt} ${tgt?.box_code || xferTo}?`))) return;
    setXferBusy(true);
    try {
      const r = await transferBox(boxId, xferTo, q);
      toast(`✅ Đã chuyển ${soVN(q)} ${pu} sang ${uTgt} ${r?.to_code || tgt?.box_code}`, "ok");
      setXferQty(""); setXferTo(null);
      reload(false);
    } catch (e: any) {
      toast(e?.message || "Lỗi chuyển hàng", "err");
    } finally {
      setXferBusy(false);
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
          <span class={"box-v bd-place" + (b.place_name ? "" : " muted")}>
            <Icon name="tag" size={14} /> <span class="bd-place-name">{b.place_name || "Chưa xếp"}</span>
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

      {!disabled && remaining > 0 && (
        <section class="card">
          <label class="card-label"><Icon name="truck" size={15} /> Chuyển hàng sang {(b.unit_name || "thùng").toLowerCase()} khác</label>
          <div class="row" style={{ gap: "6px" }}>
            <span style={{ flex: 1 }}>
              <SelectPopup title={`Chuyển ${b.product_code} tới…`} searchable placeholder="Chọn nơi nhận (cùng SP)"
                value={xferTo ?? ""} onChange={(v: string) => setXferTo(v ? Number(v) : null)}
                options={xferTargets.map((x) => ({
                  value: x.id,
                  label: `${x.unit_name || "Thùng"} ${(x.box_code || "").split("-").pop()} · còn ${soVN(x.remaining)} ${x.product_unit || "cây"}${x.place_name ? ` · ${x.place_name}` : ""}`,
                }))} />
            </span>
            <input class="pb-amount" style={{ width: "84px" }} type="text" inputMode="decimal"
              placeholder={`≤ ${soVN(remaining)}`} value={xferQty}
              onFocus={(e: any) => (e.target as HTMLInputElement).select()}
              onInput={(e: any) => setXferQty(e.target.value)} />
            <button class="btn primary" disabled={xferBusy || !xferTo} onClick={doTransfer}>Chuyển</button>
          </div>
          {(() => {
            // Preview còn lại NGAY khi gõ: bên này giảm, bên nhận tăng — đúng đơn vị từng bên
            const q = parseFloat((xferQty || "").replace(",", "."));
            const uThis = (b.unit_name || "Thùng");
            const pu = b.product_unit || "cây";
            if (!isFinite(q) || q <= 0) return (
              <div class="muted small" style={{ marginTop: "4px" }}>
                Chuyển hàng thật giữa 2 {uThis.toLowerCase()}/kệ cùng mã SP — tồn kho tổng không đổi, có lịch sử 2 chiều.
              </div>
            );
            const after = remaining - q;
            const tgt = xferTargets.find((x) => x.id === xferTo);
            return (
              <div class="small" style={{ marginTop: "4px", color: after < 0 ? "var(--danger)" : "var(--muted)" }}>
                {after < 0
                  ? `⚠ Vượt số còn lại — ${uThis.toLowerCase()} này chỉ còn ${soVN(remaining)} ${pu}`
                  : <>{uThis} này còn <b style={{ color: "var(--text)" }}>{soVN(after)} {pu}</b>
                      {tgt ? <> · {(tgt.unit_name || "thùng").toLowerCase()} {(tgt.box_code || "").split("-").pop()} thành <b style={{ color: "var(--text)" }}>{soVN((tgt.remaining || 0) + q)} {tgt.product_unit || pu}</b></> : null}
                    </>}
              </div>
            );
          })()}
        </section>
      )}

      <section class="card">
        <label class="card-label">Đã xuất / tiêu hao / chuyển</label>
        {d.allocations.length === 0 ? (
          <div class="muted small">Chưa xuất cho đơn nào — còn trong kho.</div>
        ) : (
          <ul class="box-alloc-list">
            {d.allocations.map((a) => {
              const kind = (a as any).kind || "order";
              if (kind === "transfer_out" || kind === "transfer_in") {
                const out = kind === "transfer_out";
                const peer = (a as any).peer_box_code;
                return (
                  <li key={a.allocation_id}>
                    <a class="box-jump" href={`#/thung/${a.order_thread_id}`}>
                      <Icon name="truck" size={16} />{" "}
                      {out ? "Chuyển sang" : "Nhận từ"} thùng {peer ? (peer.split("-").pop() || peer) : `#${a.order_thread_id}`}
                      {" · "}{out ? "−" : "+"}{soVN(Math.abs(a.quantity))}
                      {a.allocated_by ? ` · ${a.allocated_by}` : ""} →
                    </a>
                  </li>
                );
              }
              const prod = kind === "production";
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
