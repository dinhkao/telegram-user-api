// Chi tiết 1 thùng (#/thung/:id) — info hub: mã, số cây, tình trạng, ai nhập, ngày,
// thuộc phiếu SX nào (link), đã xuất đơn nào (link → cuộn+nháy thùng trong đơn).
// GET /api/inventory/box/:id.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { boxDetail, updateBox, setBoxDisabled, deleteBox, returnBoxMaterial, transferBox, allBoxes, listPlaces, createPlace, setBoxPlace, listUnits, createUnit, setBoxUnit, createDisposal, currentUser, soVN, type InvBoxDetail, type InvBox, type KhoBox, type Place, type Unit } from "../api";
import { onRealtime } from "../realtime";
import { fmtDateTimeVN } from "../format";
import { BoxAdjust } from "../detail/BoxAdjust";
import { QtyUnitPicker, baseChoice, toBaseQty, type UnitChoice } from "../detail/QtyUnitPicker";
import { Loading, ErrorState } from "../ui/states";
import { confirmDialog, noticeDialog, toast } from "../ui/feedback";
import { CameraBox, cameraSupported, uploadProcessed, type Processed } from "../detail/CameraBox";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { Icon } from "../ui/Icon";
import { SelectPopup } from "../ui/SelectPopup";

const isDisabled = (b: InvBox) => !!b.disabled;

export function BoxDetail({ boxId, focus }: { boxId: string; focus?: string }) {
  // Deep-link từ timeline kho: ?focus=hist:<ts> → History cuộn + nháy thao tác đó
  const focusTs = focus?.startsWith("hist-") ? Number(focus.slice(5)) : undefined;
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
          setErr("");
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
      toast(e?.message || "Lỗi lưu ghi chú", "err");
    }
  };

  const saveMfg = async (v: string) => {
    if (!d || v === (d.box.mfg_date || "")) return;
    try {
      const b = await updateBox(boxId, { mfg_date: v });
      if (b) setD({ ...d, box: b });
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu ngày SX", "err");
    }
  };

  const isAdmin = currentUser()?.role === "admin";
  const doDelete = async () => {
    if (!d) return;
    // Server tính lý do khoá xoá (đã xuất/chuyển, phiếu nhập đang chốt, phiếu trả
    // đã xử lý) → nút mờ, bấm chỉ toast lý do (server cũng chặn thật)
    if (d.delete_lock) {
      toast(d.delete_lock.reason, "info"); return;
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
        await noticeDialog(`Đã hoàn nguyên liệu về kho:\n${lines.join("\n")}`);
      }
      const code = d.box.product_code;
      window.location.hash = `#/kho/${encodeURIComponent(code)}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá thùng", "err");
      setDisBusy(false);
    }
  };

  // Trả về nguyên liệu: rã 1 thùng nguyên kiện (KDXDB5…) → hoàn toàn bộ NL theo công thức
  const doReturnMaterial = async () => {
    if (!d) return;
    if (d.allocations.length > 0) { toast("Thùng đã xuất/chuyển — thu hồi trước khi rã", "info"); return; }
    const packed = d.packed_materials || [];
    const matTxt = packed.length ? packed.map((p) => `${soVN(p.amount)} ${p.code}`).join(", ") : "nguyên liệu theo công thức";
    if (!(await confirmDialog(
      `Rã thùng ${d.box.box_code} (${d.box.product_code}) → trả về ${matTxt} vào kho.\n`
      + `Thùng sẽ được đánh dấu "đã trả về nguyên liệu" (giữ lịch sử).\nTiếp tục?`,
      { danger: true, okLabel: "Trả về NL" }))) return;
    setDisBusy(true); setErr("");
    try {
      const r = await returnBoxMaterial(boxId);
      const rest = r?.restored_materials || [];
      if (rest.length) {
        const lines = rest.flatMap((m) => (m.boxes || []).map(
          (bx: any) => `• ${soVN(bx.amount)} ${m.code} → thùng ${bx.box_code}${bx.fresh ? " (mới)" : ""}`));
        await noticeDialog(`Đã trả về nguyên liệu:\n${lines.join("\n")}`);
      }
      reload(false);
    } catch (e: any) {
      toast(e?.message || "Lỗi trả về nguyên liệu", "err");
    } finally {
      setDisBusy(false);
    }
  };

  // Chuyển hàng sang thùng khác cùng SP
  const [xferTargets, setXferTargets] = useState<KhoBox[]>([]);
  const [xferTo, setXferTo] = useState<number | null>(null);
  const [xferQty, setXferQty] = useState("");
  const [xferBusy, setXferBusy] = useState(false);
  // Đơn vị NHẬP số chuyển/hủy/điều chỉnh (gốc + quy đổi của SP) — số gửi API luôn quy về GỐC
  const [xferUnit, setXferUnit] = useState<UnitChoice | null>(null);
  const [dispUnit, setDispUnit] = useState<UnitChoice | null>(null);
  useEffect(() => { setXferUnit(null); setDispUnit(null); }, [d?.box?.id]);
  const xu = xferUnit || baseChoice(d?.box?.product_unit);
  const du = dispUnit || baseChoice(d?.box?.product_unit);
  useEffect(() => {
    if (!d) return;
    allBoxes().then((bs) => setXferTargets(
      bs.filter((x) => x.product_code === d.box.product_code && x.id !== d.box.id && !x.disabled),
    )).catch(() => {});
  }, [d?.box?.id, d?.box?.product_code]);
  const doTransfer = async () => {
    if (!d) return;
    const raw = parseFloat((xferQty || "").replace(",", "."));
    const q = toBaseQty(raw, xu);   // số ĐƠN VỊ GỐC gửi API
    const rem = d.box.remaining ?? d.box.quantity;
    if (!xferTo) { toast("Chọn thùng đích", "err"); return; }
    if (!isFinite(q) || q <= 0) { toast("Số lượng phải > 0", "err"); return; }
    if (q > rem) { toast(`Thùng chỉ còn ${soVN(rem)}`, "err"); return; }
    const tgt = xferTargets.find((x) => x.id === xferTo);
    const uThis = (d.box.unit_name || "thùng").toLowerCase();
    const uTgt = (tgt?.unit_name || "thùng").toLowerCase();
    const pu = d.box.product_unit || "cây";
    const qTxt = xu.factor !== 1 ? `${soVN(raw)} ${xu.name} (= ${soVN(q)} ${pu})` : `${soVN(q)} ${pu}`;
    if (!(await confirmDialog(`Chuyển ${qTxt} ${d.box.product_code} từ ${uThis} ${d.box.box_code} → ${uTgt} ${tgt?.box_code || xferTo}?`))) return;
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

  // Xuất hủy: hàng hư/hết hạn/vỡ → BẮT BUỘC chụp ảnh chứng từ → tạo phiếu + trừ tồn.
  // Pattern photo-first (như ProductionBoxes): chụp trước vào buffer, đóng camera mới
  // tạo phiếu rồi upload ảnh vào phiếu. Không có camera (HTTP dev) → tạo không ảnh.
  const [dispQty, setDispQty] = useState("");
  const [dispReason, setDispReason] = useState("");
  const [dispBusy, setDispBusy] = useState(false);
  const [dispCamOpen, setDispCamOpen] = useState(false);
  const dispCapsRef = useRef<Processed[]>([]);
  const dispPendingRef = useRef<{ q: number; reason: string } | null>(null);

  const doDispose = async () => {
    if (!d) return;
    const rem = d.box.remaining ?? d.box.quantity;
    const raw = parseFloat((dispQty || "").replace(",", "."));
    const q = toBaseQty(raw, du);   // số ĐƠN VỊ GỐC gửi API
    const reason = dispReason.trim();
    if (!isFinite(q) || q <= 0) { toast("Số lượng hủy phải > 0", "err"); return; }
    if (q > rem) { toast(`Thùng chỉ còn ${soVN(rem)}`, "err"); return; }
    if (!reason) { toast("Cần nhập lý do hủy", "err"); return; }
    const pu = d.box.product_unit || "cây";
    const qTxt = du.factor !== 1 ? `${soVN(raw)} ${du.name} (= ${soVN(q)} ${pu})` : `${soVN(q)} ${pu}`;
    const camOk = cameraSupported();
    if (!(await confirmDialog(
      `Xuất hủy ${qTxt} ${d.box.product_code} khỏi thùng ${d.box.box_code}?\nLý do: ${reason}\nTồn kho sẽ trừ ngay.` +
      (camOk ? "\n📸 Cần CHỤP ẢNH hàng hủy mới tạo được phiếu." : ""),
      { danger: true, okLabel: camOk ? "Chụp ảnh & hủy" : "Xuất hủy" }))) return;
    dispPendingRef.current = { q, reason };
    if (camOk) { dispCapsRef.current = []; setDispCamOpen(true); }   // tạo phiếu khi đóng camera
    else await finalizeDispose([], false);                          // HTTP dev: không ép ảnh
  };

  const finalizeDispose = async (caps: Processed[], requirePhoto: boolean) => {
    const pend = dispPendingRef.current;
    if (!d || !pend) return;
    dispPendingRef.current = null;
    if (requirePhoto && caps.length === 0) {
      toast("⚠ Chưa chụp ảnh — CHƯA xuất hủy. Bấm lại để làm.", "err");
      return;
    }
    const pu = d.box.product_unit || "cây";
    setDispBusy(true);
    try {
      const slip = await createDisposal([{ box_id: d.box.id, quantity: pend.q }], pend.reason);
      for (const p of caps) await Promise.allSettled([uploadProcessed(`/api/media/disposal/${slip.id}`, p)]);
      toast(`✅ Đã hủy ${soVN(pend.q)} ${pu} — phiếu #${slip.id}${caps.length ? ` · ${caps.length} ảnh` : ""}`, "ok");
      setDispQty(""); setDispReason("");
      reload(false);
    } catch (e: any) {
      toast(e?.message || "Lỗi xuất hủy", "err");
    } finally {
      setDispBusy(false);
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
      toast(e?.message || "Lỗi cập nhật", "err");
    } finally {
      setDisBusy(false);
    }
  };

  if (loading) return <Loading />;
  if (err || !d)
    return (
      <>
        <ErrorState msg={err || "Không tìm thấy thùng"} onRetry={() => reload(true)} />
        <p class="muted center"><a href="#/kho">← Kho</a></p>
      </>
    );

  const b = d.box;
  const backCode = b.product_code;
  const used = b.allocated ?? 0;
  const remaining = b.remaining ?? b.quantity;
  const disabled = isDisabled(b);
  // Thùng ĐÃ XUẤT HẾT (remaining ≤ 0) = read-only: chỉ trao đổi (bình luận/ảnh),
  // cấm sửa ghi chú/ngày SX/đơn vị/CHUYỂN KHO/chuyển hàng. Server cũng chặn.
  const soldOut = remaining <= 0;

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

      <a class="btn block pt-open-btn" href={`#/thung/${b.id}/timeline`}>
        <Icon name="history" size={16} /> Timeline biến động thùng →
      </a>

      {disabled && (
        <div class="box-disabled-banner">
          🚫 Thùng đã bị vô hiệu — không tính tồn kho, không phân bổ đơn, không tính vào phiếu SX.
          {b.disabled_reason ? (
            <div class="box-disabled-reason">Lý do: {b.disabled_reason}</div>
          ) : null}
        </div>
      )}

      {!disabled && soldOut && !b.reserved && (
        <div class="box-disabled-banner">
          ✅ Thùng đã xuất hết — chỉ trao đổi (bình luận/ảnh). Không sửa ghi chú/ngày
          SX/đơn vị, không chuyển kho, không chuyển hàng.
        </div>
      )}

      {!disabled && b.reserved && (
        <div class="box-reserved-banner">
          Thùng đang TẠM giữ cho đơn chưa chốt xuất kho — vẫn có thể thu hồi lại.
        </div>
      )}

      <section class="card">
        {(() => {
          // Vai 👁: kèm số quy đổi theo đơn vị hiển thị ("= 3 Thùng") cạnh số gốc
          const df = b.display_unit_factor && b.display_unit_factor > 0 && b.display_unit_factor !== 1 ? b.display_unit_factor : null;
          const dq = (v: number) => {
            const x = v / df!; const r = Math.round(x);
            return Math.abs(x - r) < 1e-6 ? soVN(r) : soVN(Math.round(x * 10) / 10);
          };
          return (
            <>
              <div class="box-kv">
                <span class="box-k">Số {b.product_unit || "cây"}</span>
                <span class="box-v big">{soVN(b.quantity)}</span>
                {df ? <span class="muted small">= {dq(b.quantity)} {b.display_unit_name}</span> : null}
              </div>
              <div class="box-kv">
                <span class="box-k">Còn lại</span>
                <span class={"box-v big " + (remaining > 0 ? "t-ok" : "t-warn")}>
                  {soVN(remaining)}
                </span>
                <span class="muted small">
                  {df ? `= ${dq(remaining)} ${b.display_unit_name}` : ""}
                  {df && used > 0 ? " · " : ""}
                  {used > 0 ? `đã xuất ${soVN(used)}` : ""}
                </span>
              </div>
            </>
          );
        })()}
        <div class="box-kv">
          <span class="box-k">Đơn vị</span>
          {soldOut ? (
            <span class="box-v">{b.unit_name || "Thùng"}</span>
          ) : (
            <SelectPopup title="Đơn vị chứa" placeholder="Thùng (mặc định)" searchable onCreate={createUnitAssign}
              value={b.unit_id ?? ""} options={units.map((u) => ({ value: u.id, label: u.name }))}
              onChange={pickUnit} />
          )}
        </div>
        <div class="box-kv">
          <span class="box-k">Vị trí</span>
          {b.place_id ? (
            <a class="box-v bd-place bd-place-link" href={`#/vi-tri/${b.place_id}`} title={b.place_name || ""}>
              <Icon name="box" size={14} /> <span class="bd-place-name">{b.place_name || `Kho #${b.place_id}`}</span>
              <Icon name="chevronRight" size={15} class="bd-place-arrow" />
            </a>
          ) : (
            <span class="box-v bd-place muted"><Icon name="tag" size={14} /> <span class="bd-place-name">Chưa xếp</span></span>
          )}
          {!soldOut && (
            <button class="btn small box-move-btn" onClick={() => setMovePop(true)} title="Chuyển kho khác">
              <Icon name="truck" size={16} />
            </button>
          )}
        </div>
        {!soldOut && (
          <SelectPopup open={movePop} onClose={() => setMovePop(false)}
            title={`Chuyển thùng ${b.box_code} tới…`} searchable onCreate={createPlaceAssign}
            value={b.place_id ?? ""}
            options={[{ value: "", label: "— Chưa xếp —" }, ...places.map((p) => ({ value: p.id, label: p.name }))]}
            onChange={doMove} />
        )}
        <div class="box-kv">
          <span class="box-k">Ngày SX</span>
          {soldOut ? (
            <span class="box-v">{mfgInput || "—"}</span>
          ) : (
            <input
              class="box-mfg"
              type="date"
              value={mfgInput}
              onInput={(e) => setMfgInput((e.target as HTMLInputElement).value)}
              onChange={(e) => saveMfg((e.target as HTMLInputElement).value)}
            />
          )}
        </div>
        <div class="box-kv">
          <span class="box-k">Người nhập</span>
          <span class="box-v">{b.created_by || "—"}</span>
        </div>
        <div class="box-kv">
          <span class="box-k">Ngày nhập</span>
          <span class="box-v">{fmtDateTimeVN(b.created_at) || "—"}</span>
        </div>
      </section>

      <section class="card">
        <label class="card-label">Ghi chú {noteSaved && <span class="muted small">✓ đã lưu</span>}</label>
        {soldOut ? (
          <div class={b.note ? "" : "muted small"}>{b.note || "Không có ghi chú"}</div>
        ) : (
          <textarea
            rows={2}
            value={noteInput}
            onInput={(e) => setNoteInput((e.target as HTMLTextAreaElement).value)}
            onBlur={saveNote}
            placeholder="Ghi chú cho thùng (tự lưu khi rời ô)…"
          />
        )}
      </section>

      <section class="card">
        <label class="card-label">Nguồn — {d.source_purchase ? "Phiếu nhập hàng" : d.source_return ? "Phiếu trả hàng" : "Phiếu sản xuất"}</label>
        {d.source_slip ? (
          <a class="box-jump" href={`#/san_xuat/${d.source_slip.thread_id}?focus=box:${b.id}`}>
            <Icon name="factory" size={16} /> {d.source_slip.sp_name || b.product_code}
            {d.source_slip.date ? ` · ${d.source_slip.date}` : ""} →
          </a>
        ) : d.source_purchase ? (
          <a class="box-jump" href={`#/nhap-hang/${d.source_purchase.id}`}>
            <Icon name="truck" size={16} /> Nhập hàng {d.source_purchase.supplier_name ? `NCC ${d.source_purchase.supplier_name}` : `#${d.source_purchase.id}`}
            {d.source_purchase.created_at ? ` · ${d.source_purchase.created_at.slice(8, 10)}/${d.source_purchase.created_at.slice(5, 7)}` : ""} →
          </a>
        ) : d.source_return ? (
          <a class="box-jump" href={`#/tra-hang/${d.source_return.id}`}>
            <Icon name="truck" size={16} /> Hàng trả về #{d.source_return.id}
            {d.source_return.created_at ? ` · ${d.source_return.created_at.slice(8, 10)}/${d.source_return.created_at.slice(5, 7)}` : ""} →
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
              placeholder={`≤ ${soVN(xu.factor !== 1 ? Math.round(remaining / xu.factor * 10) / 10 : remaining)}`} value={xferQty}
              onFocus={(e: any) => (e.target as HTMLInputElement).select()}
              onInput={(e: any) => setXferQty(e.target.value)} />
            <QtyUnitPicker code={b.product_code} baseUnit={b.product_unit} unit={xu} onPick={setXferUnit} />
            {(() => {
              // Chưa đủ điều kiện (thiếu đích / số sai / vượt còn lại) → FADE, bấm toast lý do
              const q = toBaseQty(parseFloat((xferQty || "").replace(",", ".")), xu);
              const ok = !!xferTo && isFinite(q) && q > 0 && q <= remaining;
              return (
                <button class={"btn primary" + (ok ? "" : " faded")} disabled={xferBusy} onClick={doTransfer}
                  title={ok ? undefined : "Chọn thùng đích + số lượng hợp lệ"}>Chuyển</button>
              );
            })()}
          </div>
          {(() => {
            // Preview còn lại NGAY khi gõ: bên này giảm, bên nhận tăng — đúng đơn vị từng bên
            const q = toBaseQty(parseFloat((xferQty || "").replace(",", ".")), xu);
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

      {!disabled && remaining > 0 && (
        <section class="card">
          <label class="card-label"><Icon name="trash" size={15} /> Xuất hủy (hàng hư / hết hạn / vỡ)</label>
          <div class="row" style={{ gap: "6px" }}>
            <input class="pb-amount" style={{ width: "84px" }} type="text" inputMode="decimal"
              placeholder={`≤ ${soVN(du.factor !== 1 ? Math.round(remaining / du.factor * 10) / 10 : remaining)}`} value={dispQty}
              onFocus={(e: any) => (e.target as HTMLInputElement).select()}
              onInput={(e: any) => setDispQty(e.target.value)} />
            <QtyUnitPicker code={b.product_code} baseUnit={b.product_unit} unit={du} onPick={setDispUnit} />
            <input style={{ flex: 1, minWidth: 0 }} type="text" placeholder="Lý do hủy (bắt buộc)"
              value={dispReason} onInput={(e: any) => setDispReason(e.target.value)} />
            {(() => {
              const q = toBaseQty(parseFloat((dispQty || "").replace(",", ".")), du);
              const ok = isFinite(q) && q > 0 && q <= remaining && !!dispReason.trim();
              return (
                <button class={"btn danger" + (ok ? "" : " faded")} disabled={dispBusy} onClick={doDispose}
                  title={ok ? undefined : "Nhập số lượng hợp lệ + lý do"}>Hủy</button>
              );
            })()}
          </div>
          <div class="muted small" style={{ marginTop: "4px" }}>
            {cameraSupported() ? "📸 Bấm Hủy sẽ mở camera — chụp ảnh hàng hủy mới tạo phiếu. " : ""}
            Tồn thùng trừ ngay, ghi phiếu ở <a href="#/xuat-huy">Xuất hủy</a> — admin xoá phiếu sẽ hoàn tồn.
          </div>
          {dispCamOpen && (
            <CameraBox base={`/api/media/disposal/0`}
              onCapture={(p) => { dispCapsRef.current.push(p); }}
              onUploaded={() => {}}
              onClose={() => { setDispCamOpen(false); finalizeDispose(dispCapsRef.current, true); }} />
          )}
        </section>
      )}

      {!disabled && (
        <BoxAdjust boxId={b.id} remaining={remaining} unit={b.product_unit || "cây"}
          code={b.product_code} onChanged={() => reload(false)} />
      )}

      <section class="card">
        <label class="card-label">Đã xuất / tiêu hao / chuyển</label>
        {d.allocations.length === 0 ? (
          <div class="muted small">Chưa xuất cho đơn nào — còn trong kho.</div>
        ) : (
          <div class="alloc-cards">
            {d.allocations.map((a) => {
              // 1 kiểu CARD chung cho mọi loại biến động: icon tròn (đỏ ra / xanh vào)
              // + tiêu đề + người·lúc + số lượng bên phải. quantity ÂM = hàng VÀO thùng.
              const kind = (a as any).kind || "order";
              const inbound = a.quantity < 0;
              let icon = "clipboard"; let href: string | undefined; let title = "";
              if (kind === "transfer_out" || kind === "transfer_in") {
                const out = kind === "transfer_out";
                const peer = (a as any).peer_box_code;
                icon = "truck"; href = `#/thung/${a.order_thread_id}`;
                title = `${out ? "Chuyển sang" : "Nhận từ"} thùng ${peer ? (peer.split("-").pop() || peer) : `#${a.order_thread_id}`}`;
              } else if (kind === "disposal") {
                icon = "trash"; href = `#/xuat-huy/${a.order_thread_id}`;
                title = `Xuất hủy — phiếu #${a.order_thread_id}`;
              } else if (kind === "purchase_in") {
                icon = "truck"; href = `#/nhap-hang/${a.order_thread_id}`;
                title = `Hàng mua về — phiếu nhập #${a.order_thread_id}`;
              } else if (kind === "return_in") {
                icon = "refresh"; href = `#/tra-hang/${a.order_thread_id}`;
                title = `Khách trả hàng — phiếu #${a.order_thread_id}`;
              } else if (kind === "adjustment") {
                // chi tiết + gỡ phiếu nằm ở khối "Điều chỉnh tồn" phía trên
                icon = "edit"; href = "#/dieu-chinh";
                title = `Điều chỉnh tồn — phiếu #${a.order_thread_id}`;
              } else if (kind === "production") {
                icon = "factory"; href = `#/san_xuat/${a.order_thread_id}?focus=box:${b.id}`;
                title = `Tiêu hao đóng gói — phiếu SX #${a.order_thread_id}`;
              } else {
                icon = "clipboard"; href = `#/order/${a.order_thread_id}?focus=box:${b.id}`;
                title = a.order_text ? `Đơn “${a.order_text}”` : `Đơn #${a.order_thread_id}`;
              }
              const sub = [a.allocated_by, a.allocated_at ? fmtDateTimeVN(a.allocated_at) : ""].filter(Boolean).join(" · ");
              return (
                <a class="alloc-card" href={href} key={a.allocation_id}>
                  <span class={"alloc-ic " + (inbound ? "in" : "out")}><Icon name={icon as any} size={17} /></span>
                  <span class="alloc-main">
                    <span class="alloc-title">{title}</span>
                    {sub && <span class="alloc-sub">{sub}</span>}
                  </span>
                  <span class={"alloc-amt " + (inbound ? "in" : "out")}>{inbound ? "+" : "−"}{soVN(Math.abs(a.quantity))}</span>
                </a>
              );
            })}
          </div>
        )}
      </section>

      <Images base={`/api/media/box/${b.id}`} />
      <Comments base={`/api/media/box/${b.id}`} />
      <History base={`/api/media/box/${b.id}`} focusTs={focusTs} />

      {/* Vô hiệu thùng đã TẮT — chỉ còn kích hoạt lại thùng vô hiệu từ trước */}
      {disabled && (
        <section class="card">
          <button class="btn block" disabled={disBusy} onClick={reactivate}>
            {disBusy ? "…" : <><Icon name="check" size={16} /> Kích hoạt lại thùng</>}
          </button>
        </section>
      )}

      {isAdmin && !disabled && b.self_container && (
        <section class="card">
          <label class="card-label"><Icon name="refresh" size={15} /> Trả về nguyên liệu</label>
          <div class="muted small" style={{ margin: "2px 0 8px" }}>
            Rã thùng {b.product_code} này → hoàn {(d.packed_materials || []).length
              ? (d.packed_materials || []).map((p) => `${soVN(p.amount)} ${p.code}`).join(", ")
              : "nguyên liệu theo công thức"} vào kho để bán lẻ. Thùng giữ lại trong lịch sử.
          </div>
          <button class={"btn block" + (d.allocations.length > 0 ? " faded" : "")} disabled={disBusy} onClick={doReturnMaterial}
            title={d.allocations.length > 0 ? "Đã xuất cho đơn — thu hồi trước" : undefined}>
            <Icon name="refresh" size={16} /> {disBusy ? "…" : "Trả về nguyên liệu"}
          </button>
        </section>
      )}

      {/* Admin xoá mọi thùng; người dùng thường xoá thùng của PHIẾU NHẬP (server
          chỉ cho khi phiếu đang mở — phiếu chốt thì delete_lock làm mờ nút kèm lý do). */}
      {(isAdmin || !!d.box.source_purchase_id) && (
        <section class="card">
          <button class={"btn danger block" + (d.delete_lock ? " faded" : "")} disabled={disBusy} onClick={doDelete}
            title={d.delete_lock?.reason}>
            <Icon name="trash" size={16} /> Xoá thùng{isAdmin ? " (admin)" : ""}
          </button>
          {d.delete_lock && (
            <div class="muted small">
              {d.delete_lock.reason}
              {d.delete_lock.href && <>{" — "}<a href={d.delete_lock.href}>mở phiếu</a></>}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
