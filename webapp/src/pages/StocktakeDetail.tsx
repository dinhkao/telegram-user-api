import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  applyStocktake, completeStocktake, getStocktake, isOffice, lockStocktake, resyncStocktake, saveStocktake,
  soVN, unlockStocktake, voidStocktake,
  type Stocktake, type StocktakeItem,
} from "../api";
import { foldVN, fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { PageHead } from "../ui/PageHead";
import { BoxTile } from "../detail/BoxTile";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";
import { SearchBar } from "../ui/SearchBar";
import { EmptyState, ErrorState, Loading } from "../ui/states";

type Filter = "all" | "pending" | "diff";

const num = (v: string) => v.trim() === "" ? null : Number(v);
const signed = (v: number) => `${v > 0 ? "+" : ""}${soVN(v)}`;

export function StocktakeDetail({ id }: { id: string }) {
  const sid = useMemo(() => Math.random().toString(36).slice(2) + Date.now().toString(36), []);
  const [slip, setSlip] = useState<Stocktake | null>(null);
  const [values, setValues] = useState<Record<number, string>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [note, setNote] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [holder, setHolder] = useState<string | null>(null);
  const [lockState, setLockState] = useState<"wait" | "mine" | "other">("wait");
  const [saveState, setSaveState] = useState<"" | "saving" | "saved" | "error">("");
  const autoTimer = useRef<any>(null);
  const saveChain = useRef<Promise<any>>(Promise.resolve());
  const aliveRef = useRef(true);
  const dirtyRef = useRef(false);
  const versionRef = useRef(0);
  const [editVersion, setEditVersion] = useState(0);
  const latestRef = useRef<{ counts: { id: number; actual_quantity?: number | null; counted_bulk?: number | null; counted_loose?: number | null; note?: string }[]; note: string }>({ counts: [], note: "" });
  // Đơn vị KIỂM bắt buộc (vai 📋, snapshot trên item): nhập kép [N kiện] + [M lẻ] —
  // values vẫn giữ TỔNG đơn vị gốc (mọi thống kê/lệch tính như cũ), raw gửi server.
  const [bulkVals, setBulkVals] = useState<Record<number, string>>({});
  const [looseVals, setLooseVals] = useState<Record<number, string>>({});
  const initRaw = (it: StocktakeItem): [string, string] => {
    if (!it.count_unit_factor) return ["", ""];
    if (it.counted_bulk != null || it.counted_loose != null)
      return [it.counted_bulk == null ? "" : String(it.counted_bulk), it.counted_loose == null ? "" : String(it.counted_loose)];
    return ["", it.actual_quantity == null ? "" : String(it.actual_quantity)];   // dữ liệu cũ chỉ có tổng
  };

  const adopt = (d: Stocktake) => {
    setSlip(d);
    setValues(Object.fromEntries(d.items.map((it) => [it.id, it.actual_quantity == null ? "" : String(it.actual_quantity)])));
    setBulkVals(Object.fromEntries(d.items.map((it) => [it.id, initRaw(it)[0]])));
    setLooseVals(Object.fromEntries(d.items.map((it) => [it.id, initRaw(it)[1]])));
    setNotes(Object.fromEntries(d.items.map((it) => [it.id, it.note || ""])));
    setNote(d.note || "");
  };
  const load = () => {
    setErr("");
    getStocktake(id).then(adopt).catch((e: any) => setErr(e?.message || "Lỗi tải phiếu kiểm kho"));
  };
  useEffect(load, [id]);

  // Kho biến động khi đang kiểm → tải lại số sổ sách + cờ lỗi thời, GIỮ số đang gõ dở
  // (không adopt: values/notes là state riêng, chỉ cập nhật slip = expected + stale + status).
  const reloadStale = () => { getStocktake(id).then(setSlip).catch(() => {}); };

  const acquire = async () => {
    if (!aliveRef.current) return;
    try {
      const r = await lockStocktake(id, sid);
      if (!aliveRef.current) {
        if (r.mine) unlockStocktake(id, sid).catch(() => {});
        return;
      }
      if (r.completed) return;
      setHolder(r.holder);
      setLockState(r.mine ? "mine" : "other");
    } catch { /* heartbeat sẽ thử lại */ }
  };
  useEffect(() => {
    aliveRef.current = true;
    acquire();
    const hb = setInterval(acquire, 20000);
    return () => {
      aliveRef.current = false;
      clearInterval(hb); clearTimeout(autoTimer.current);
      // Rời trang vẫn flush thay đổi cuối rồi mới nhả khóa.
      saveChain.current = saveChain.current.catch(() => {}).then(() => dirtyRef.current
        ? saveStocktake(id, latestRef.current.counts, latestRef.current.note, sid).catch(() => null)
        : null).finally(() => unlockStocktake(id, sid).catch(() => {}));
    };
  }, [id]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "stocktake_lock" && e.stocktake_id === String(id)) acquire();
    if (e.type === "inventory_changed" || e.type === "box_changed" || e.type === "resync") reloadStale();
  }), [id]);

  const computed = useMemo(() => {
    if (!slip) return { counted: 0, expected: 0, actual: 0, diff: 0, deviations: 0 };
    let counted = 0, expected = 0, actual = 0, deviations = 0;
    for (const it of slip.items) {
      expected += it.expected_quantity;
      const a = num(values[it.id] ?? "");
      if (a != null && Number.isFinite(a)) {
        counted++; actual += a;
        if (Math.abs(a - it.expected_quantity) > 1e-9) deviations++;
      }
    }
    return { counted, expected, actual, diff: actual - expected, deviations };
  }, [slip, values]);

  const visible = useMemo(() => {
    if (!slip) return [];
    const query = foldVN(q.trim());
    return slip.items.filter((it) => {
      const a = num(values[it.id] ?? "");
      const diff = a == null ? null : a - it.expected_quantity;
      if (filter === "pending" && a != null) return false;
      if (filter === "diff" && (diff == null || Math.abs(diff) <= 1e-9)) return false;
      return !query || foldVN(`${it.product_code} ${it.box_code}`).includes(query);
    });
  }, [slip, values, filter, q]);

  const visibleGroups = useMemo(() => {
    if (!slip) return [];
    const shown = new Map<string, StocktakeItem[]>();
    for (const it of visible) {
      const code = it.product_code || "Chưa có mã";
      shown.set(code, [...(shown.get(code) || []), it]);
    }
    return [...shown.entries()].map(([code, items]) => {
      const all = slip.items.filter((it) => (it.product_code || "Chưa có mã") === code);
      // Sổ = tổng expected của mã; Đếm = tổng actual đã nhập; Lệch = Đếm − Sổ (chỉ
      // đủ nghĩa khi ĐẾM HẾT mọi thùng của mã → hiện khi counted === total).
      let counted = 0, deviations = 0, expected = 0, actual = 0;
      for (const it of all) {
        expected += it.expected_quantity;
        const a = num(values[it.id] ?? "");
        if (a == null || !Number.isFinite(a)) continue;
        counted += 1;
        actual += a;
        if (Math.abs(a - it.expected_quantity) > 1e-9) deviations += 1;
      }
      const diff = counted === all.length ? actual - expected : null;
      return { code, items, counted, total: all.length, deviations, expected, actual, diff,
               unit: all[0]?.product_unit || "" };
    });
  }, [slip, visible, values]);

  const counts = () => (slip?.items || []).map((it) => {
    if ((it.count_unit_factor || 0) > 0) {
      const cb = bulkVals[it.id] ?? "", cl = looseVals[it.id] ?? "";
      return { id: it.id, counted_bulk: cb === "" ? null : num(cb),
               counted_loose: cl === "" ? null : num(cl), note: notes[it.id] || "" };
    }
    return { id: it.id, actual_quantity: num(values[it.id] ?? ""), note: notes[it.id] || "" };
  });
  const valid = () => Object.values(values).every((v) => {
    const n = num(v); return n == null || (Number.isFinite(n) && n >= 0);
  });
  latestRef.current = { counts: counts(), note };
  const markDirty = () => {
    dirtyRef.current = true;
    versionRef.current += 1;
    setEditVersion(versionRef.current);
    setSaveState("");
  };
  const save = async () => {
    if (!slip || !valid()) { toast("Số thực tế phải là số không âm", "err"); return null; }
    setBusy(true);
    try {
      await saveChain.current.catch(() => {});
      const d = await saveStocktake(slip.id, counts(), note, sid);
      dirtyRef.current = false;
      setSaveState("saved");
      adopt(d);
      toast("Đã lưu phiếu kiểm kho", "ok");
      return d;
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu phiếu", "err");
      return null;
    } finally { setBusy(false); }
  };
  const finish = async () => {
    if (!slip || computed.counted !== slip.items.length) {
      setFilter("pending");
      toast(`Còn ${(slip?.items.length || 0) - computed.counted} thùng chưa kiểm`, "err");
      return;
    }
    if (slip.stale?.changed) { toast("Kho đã biến động — cập nhật lại phiếu trước khi hoàn tất", "err"); return; }
    if (!valid()) { toast("Số thực tế phải là số không âm", "err"); return; }
    const ok = await confirmDialog(
      computed.deviations
        ? `Hoàn tất phiếu với ${computed.deviations} thùng lệch, tổng lệch ${signed(computed.diff)}?`
        : "Tất cả thùng đều khớp số hệ thống. Hoàn tất phiếu?",
      { okLabel: "Hoàn tất" },
    );
    if (!ok) return;
    setBusy(true);
    try {
      clearTimeout(autoTimer.current);
      await saveChain.current.catch(() => {});
      let d = await saveStocktake(slip.id, counts(), note, sid);
      d = await completeStocktake(d.id, note, sid);
      dirtyRef.current = false;
      adopt(d); toast("Đã hoàn tất kiểm kho", "ok");
      // Có thùng lệch → mời áp dụng vào kho luôn (tạo phiếu điều chỉnh từng thùng)
      if (isOffice() && (d.summary?.deviation_count || 0) > 0 && !d.applied_at
        && await confirmDialog(`Có ${d.summary.deviation_count} thùng lệch — áp dụng số đếm vào kho ngay? (tạo phiếu điều chỉnh cho từng thùng)`, { okLabel: "Áp dụng" })) {
        await applyNow(d.id);
      }
    } catch (e: any) {
      toast(e?.message || "Lỗi hoàn tất phiếu", "err");
      reloadStale();   // có thể bị chặn vì kho vừa biến động → hiện banner cảnh báo
    }
    finally { setBusy(false); }
  };
  // Tách 1 tổng (đơn vị gốc) thành [N kiện, M lẻ] theo factor của dòng — cho nút "Đủ".
  const splitRaw = (it: StocktakeItem, total: number): [string, string] => {
    const f = it.count_unit_factor || 0;
    if (f <= 0) return ["", String(total)];
    const b = Math.floor(total / f + 1e-9);
    const l = Math.round((total - b * f) * 1e6) / 1e6;
    return [String(b), String(l)];
  };
  const fillMatched = () => {
    if (!slip) return;
    const empty = (v: string | undefined) => v === "" || v == null;
    setValues((old) => ({ ...old, ...Object.fromEntries(slip.items.map((it) => [it.id, empty(old[it.id]) ? String(it.expected_quantity) : old[it.id]])) }));
    setBulkVals((old) => ({ ...old, ...Object.fromEntries(slip.items.filter((it) => (it.count_unit_factor || 0) > 0 && empty(values[it.id])).map((it) => [it.id, splitRaw(it, it.expected_quantity)[0]])) }));
    setLooseVals((old) => ({ ...old, ...Object.fromEntries(slip.items.filter((it) => (it.count_unit_factor || 0) > 0 && empty(values[it.id])).map((it) => [it.id, splitRaw(it, it.expected_quantity)[1]])) }));
    markDirty();
  };
  // Kho biến động → đồng bộ lại số sổ sách theo tồn hiện tại, GIỮ số đã đếm. Gỡ cờ lỗi thời.
  const resync = async () => {
    if (!slip) return;
    setBusy(true);
    try {
      clearTimeout(autoTimer.current);
      await saveChain.current.catch(() => {});
      if (dirtyRef.current && valid()) await saveStocktake(slip.id, counts(), note, sid).catch(() => {});
      dirtyRef.current = false;
      const d = await resyncStocktake(slip.id, sid);
      adopt(d);   // dòng thùng thay đổi (thêm/bớt/đổi số) → nạp lại map số đếm từ bản đã lưu
      setSaveState("");
      toast("Đã cập nhật phiếu theo tồn kho hiện tại", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi cập nhật phiếu", "err"); }
    finally { setBusy(false); }
  };
  // ÁP DỤNG chênh lệch vào kho (văn phòng, phiếu đã chốt, 1 lần) — server tạo phiếu
  // điều chỉnh theo DELTA từng thùng lệch, all-or-nothing.
  const applyNow = async (id?: number) => {
    if (!slip && !id) return;
    setBusy(true);
    try {
      const d = await applyStocktake(id ?? slip!.id);
      adopt(d);
      toast(`Đã áp dụng vào kho — điều chỉnh ${(d.applied_result?.adjusted || []).length} thùng`, "ok");
    } catch (e: any) { toast(e?.message || "Không áp dụng được", "err"); }
    finally { setBusy(false); }
  };
  // Huỷ phiếu (văn phòng) — bỏ số đã kiểm, giải phóng vị trí cho phiếu mới.
  const voidSlip = async () => {
    if (!slip) return;
    if (!(await confirmDialog("Huỷ phiếu kiểm kho này? Số đã kiểm sẽ bị bỏ. Bạn có thể tạo phiếu mới cho vị trí.", { danger: true, okLabel: "Huỷ phiếu" }))) return;
    setBusy(true);
    try {
      await voidStocktake(slip.id);
      toast("Đã huỷ phiếu kiểm kho", "ok");
      window.location.hash = `#/vi-tri/${slip.place_id}`;
    } catch (e: any) { toast(e?.message || "Lỗi huỷ phiếu", "err"); setBusy(false); }
  };

  // Tự lưu tuần tự sau khi ngừng gõ 900ms; request cũ luôn xong trước request mới.
  useEffect(() => {
    if (!slip || slip.status !== "draft" || lockState !== "mine" || editVersion <= 0 || !dirtyRef.current || !valid()) return;
    clearTimeout(autoTimer.current);
    const version = editVersion;
    const snapshot = { counts: counts(), note };
    autoTimer.current = setTimeout(() => {
      setSaveState("saving");
      saveChain.current = saveChain.current.catch(() => {}).then(() => saveStocktake(slip.id, snapshot.counts, snapshot.note, sid))
        .then((d) => {
          // Mang theo cờ lỗi thời từ response → banner "kho biến động" hiện ngay cả khi
          // đang gõ (không cần chờ realtime). Giữ nguyên values/notes người dùng.
          setSlip((old) => old ? { ...old, updated_at: d.updated_at, updated_by: d.updated_by, stale: d.stale } : old);
          if (versionRef.current === version) { dirtyRef.current = false; setSaveState("saved"); }
        })
        .catch(() => { setSaveState("error"); acquire(); });
    }, 900);
    return () => clearTimeout(autoTimer.current);
  }, [editVersion, lockState]);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!slip) return <Loading />;
  const done = slip.status === "completed";
  const voided = slip.status === "voided";
  const mine = !done && !voided && lockState === "mine";
  const readOnly = done || voided || !mine;
  const allCounted = computed.counted === slip.items.length;
  const totalDiff = done ? (slip.summary.difference_total || 0) : computed.diff;
  const stale = !done && !voided && !!slip.stale?.changed;

  return (
    <div class="stocktake-page">
      <PageHead fallback={`#/vi-tri/${slip.place_id}`}
        title={<><Icon name="clipboard" size={18} /> Phiếu kiểm kho #{slip.id}</>}
        sub={<>{slip.place_name} · chụp lúc {fmtDateTimeVN(slip.captured_at)}</>}
        right={
          <span class={`stocktake-status ${done ? "done" : voided ? "voided" : lockState}`}>
            {done ? "Đã chốt" : voided ? "Đã huỷ" : lockState === "mine" ? "Bạn đang kiểm" : lockState === "other" ? `${holder} đang kiểm` : "Đang xin quyền…"}
          </span>
        } />

      {voided && (
        <div class="stocktake-lock-alert voided"><Icon name="ban" size={16} /> Phiếu này đã bị huỷ. Số đã kiểm không được ghi nhận — tạo phiếu mới ở trang vị trí kho.</div>
      )}

      {stale && (
        <div class="stocktake-stale-alert">
          <div class="stocktake-stale-head"><Icon name="ban" size={16} /> <b>Kho đã biến động — phiếu không còn chính xác</b></div>
          <p class="small">{slip.stale!.summary} sau khi tạo phiếu. Số sổ sách đã lệch khỏi tồn hiện tại; phải cập nhật lại phiếu trước khi hoàn tất.</p>
          <StaleDetails stale={slip.stale!} />
          <div class="stocktake-stale-actions">
            {mine && <button class="btn small primary" disabled={busy} onClick={resync}><Icon name="refresh" size={14} /> Cập nhật lại theo tồn hiện tại</button>}
            {!mine && lockState === "other" && <span class="muted small">{holder} đang giữ phiếu — nhờ họ cập nhật lại.</span>}
            {isOffice() && <button class="btn small danger" disabled={busy} onClick={voidSlip}><Icon name="ban" size={14} /> Huỷ phiếu</button>}
          </div>
        </div>
      )}

      {!done && !voided && lockState === "other" && (
        <div class="stocktake-lock-alert"><Icon name="lock" size={16} /> <b>{holder}</b> đang kiểm kho này. Bạn chỉ có thể xem cho đến khi họ rời phiếu.</div>
      )}

      <div class="stocktake-people">
        <span><Icon name="edit" size={14} /> Người sửa: <b>{done ? (slip.updated_by || slip.created_by || "—") : (holder || slip.updated_by || slip.created_by || "—")}</b></span>
        {done && <span><Icon name="check" size={14} /> Người chốt: <b>{slip.completed_by || "—"}</b> · {fmtDateTimeVN(slip.completed_at)}</span>}
      </div>

      {/* Áp dụng chênh lệch vào kho: phiếu đã chốt, có lệch, chưa áp → nút (văn phòng);
          đã áp → tóm tắt phiếu điều chỉnh từng thùng. */}
      {done && slip.applied_at && (
        <section class="card stocktake-applied">
          <label class="card-label"><Icon name="check" size={15} /> Đã áp dụng vào kho</label>
          <div class="muted small">{slip.applied_by || ""} · {fmtDateTimeVN(slip.applied_at)}</div>
          {(slip.applied_result?.adjusted || []).map((a) => (
            <div key={a.adjustment_id} class="small">
              {a.product_code} · <a href={`#/thung/${a.box_id}`}>thùng {(a.box_code || "").split("-").pop()}</a>
              {" "}điều chỉnh <b>{a.delta > 0 ? "+" : ""}{soVN(a.delta)}</b>
            </div>
          ))}
          {!(slip.applied_result?.adjusted || []).length && <div class="muted small">Không có thùng lệch — kho giữ nguyên.</div>}
        </section>
      )}
      {done && !slip.applied_at && (slip.summary.deviation_count || 0) > 0 && (
        <section class="card stocktake-applied">
          <label class="card-label"><Icon name="edit" size={15} /> Chênh lệch chưa áp dụng vào kho</label>
          <div class="muted small stocktake-applied-note">
            {slip.summary.deviation_count} thùng lệch so với sổ sách lúc đếm. Áp dụng sẽ tạo <b>phiếu điều
            chỉnh</b> cho từng thùng (theo mức lệch, không đè các xuất/nhập sau khi đếm) — admin gỡ được từng phiếu.
          </div>
          {isOffice()
            ? <button class="btn primary block" disabled={busy} onClick={() => applyNow()}>
                {busy ? "Đang áp dụng…" : "⚖ Áp dụng số đếm vào kho"}
              </button>
            : <div class="muted small">Chỉ văn phòng được áp dụng vào kho.</div>}
        </section>
      )}

      <section class={`stocktake-hero ${done && totalDiff === 0 ? "matched" : ""}`}>
        <div class="stocktake-progress">
          <div class="stocktake-progress-ring" style={{ "--p": `${slip.items.length ? computed.counted / slip.items.length * 100 : 100}%` } as any}>
            <b>{computed.counted}</b><small>/{slip.items.length}</small>
          </div>
          <div>
            <div class="stocktake-kicker">TIẾN ĐỘ KIỂM ĐẾM</div>
            <strong>{done ? "Đã hoàn tất" : allCounted ? "Sẵn sàng chốt phiếu" : `Còn ${slip.items.length - computed.counted} thùng`}</strong>
            <div class="muted small">Sổ sách {soVN(computed.expected)} · Thực tế {computed.counted ? soVN(computed.actual) : "—"}</div>
          </div>
        </div>
        <div class={`stocktake-delta ${allCounted || done ? (totalDiff === 0 ? "zero" : totalDiff > 0 ? "plus" : "minus") : "pending"}`}>
          <span>Chênh lệch</span>
          <b>{allCounted || done ? signed(totalDiff) : "—"}</b>
          <small>{done ? `${slip.summary.deviation_count} thùng lệch` : `${computed.deviations} lệch đã thấy`}</small>
        </div>
      </section>

      {!done && (
        <div class="stocktake-tools">
          <SearchBar value={q} onInput={setQ} placeholder="Tìm mã SP hoặc số thùng…" />
          <div class="stocktake-filter-row">
            <button class={"chip" + (filter === "all" ? " active" : "")} onClick={() => setFilter("all")}>Tất cả</button>
            <button class={"chip" + (filter === "pending" ? " active" : "")} onClick={() => setFilter("pending")}>Chưa kiểm ({slip.items.length - computed.counted})</button>
            <button class={"chip" + (filter === "diff" ? " active" : "")} onClick={() => setFilter("diff")}>Lệch ({computed.deviations})</button>
            {mine && <button class="btn small stocktake-fill" onClick={fillMatched}><Icon name="check" size={14} /> Điền phần còn lại khớp</button>}
          </div>
        </div>
      )}

      <div class="stocktake-groups">
        {visibleGroups.map((group) => (
          <section class="stocktake-product-group" key={group.code}>
            <header class="stocktake-group-head">
              <a href={`#/kho/${encodeURIComponent(group.code)}`}>
                <span>{group.code}</span>
                {group.unit && <small>{group.unit}</small>}
              </a>
              <span class="stocktake-group-progress">
                <b>{group.counted}/{group.total}</b> thùng
                {group.deviations > 0 && <em>{group.deviations} lệch</em>}
              </span>
            </header>
            {/* Sổ · Đếm · Lệch theo TỪNG MÃ — trả lời "sau khi trừ SX, thực tế hao/dư bao nhiêu" */}
            <div class="stocktake-group-nums muted small">
              Sổ {soVN(group.expected)} · Đếm {group.counted ? soVN(group.actual) : "—"}
              {group.diff != null && Math.abs(group.diff) > 1e-9 && (
                <b class={group.diff < 0 ? "t-danger" : "t-warn"}>
                  {" · Lệch "}{group.diff > 0 ? "+" : ""}{soVN(group.diff)}
                </b>
              )}
              {group.diff != null && Math.abs(group.diff) <= 1e-9 && <span class="t-ok">{" · Khớp"}</span>}
            </div>
            <div class="stocktake-list">
              {group.items.map((it) => <StocktakeRow key={it.id} item={it} value={values[it.id] ?? ""}
                bulkVal={bulkVals[it.id] ?? ""} looseVal={looseVals[it.id] ?? ""} note={notes[it.id] || ""}
                readonly={readOnly} onValue={(v) => { setValues((old) => ({ ...old, [it.id]: v })); markDirty(); }}
                onRaw={(nb, nl) => {
                  // nhập kép → tổng đơn vị gốc vào values (thống kê/lệch tính như cũ)
                  const f = it.count_unit_factor || 0;
                  setBulkVals((old) => ({ ...old, [it.id]: nb }));
                  setLooseVals((old) => ({ ...old, [it.id]: nl }));
                  const total = nb.trim() === "" && nl.trim() === "" ? "" : String((num(nb) || 0) * f + (num(nl) || 0));
                  setValues((old) => ({ ...old, [it.id]: total }));
                  markDirty();
                }}
                onNote={(v) => { setNotes((old) => ({ ...old, [it.id]: v })); markDirty(); }} />)}
            </div>
          </section>
        ))}
        {visible.length === 0 && <EmptyState>{q ? "Không có thùng khớp tìm kiếm." : filter === "pending" ? "Đã kiểm đủ mọi thùng." : filter === "diff" ? "Chưa phát hiện thùng lệch." : "Phiếu không có thùng nào."}</EmptyState>}
      </div>

      <section class="card stocktake-note">
        <label class="card-label"><Icon name="note" size={15} /> Ghi chú phiếu</label>
        {readOnly
          ? <p class={note ? "" : "muted small"}>{note || "Không có ghi chú."}</p>
          : <textarea rows={2} placeholder="Ghi chú ca kiểm, nguyên nhân chung…" value={note} onInput={(e: any) => { setNote(e.target.value); markDirty(); }} />}
      </section>

      {mine && (
        <div class="stocktake-actions">
          <div class="stocktake-actions-sum"><b>{computed.counted}/{slip.items.length}</b><span>đã kiểm</span></div>
          <div class="stocktake-autosave" data-st={saveState}>
            {saveState === "saving" ? "Đang lưu…" : saveState === "saved" ? "✓ Đã tự lưu" : saveState === "error" ? "⚠ Lỗi lưu" : "Tự lưu khi nhập"}
          </div>
          {isOffice() && <button class="btn small ghost" disabled={busy} onClick={voidSlip} title="Huỷ phiếu, bỏ số đã kiểm"><Icon name="ban" size={15} /> Huỷ</button>}
          <button class="btn" disabled={busy} onClick={() => save()}><Icon name="save" size={17} /> Lưu ngay</button>
          <button class={"btn primary" + (stale ? " faded" : "")} disabled={busy || (!allCounted && !stale)}
            onClick={() => stale ? toast("Kho đã biến động — cập nhật lại phiếu trước khi hoàn tất", "err") : finish()}>
            <Icon name="check" size={17} /> Hoàn tất
          </button>
        </div>
      )}
    </div>
  );
}

function StaleDetails({ stale }: { stale: NonNullable<Stocktake["stale"]> }) {
  const cap = <T,>(a: T[], n = 6) => a.slice(0, n);
  return (
    <div class="stocktake-stale-detail">
      {stale.adjusted.length > 0 && (
        <div><span class="st-diff-tag adj">Đổi số</span>
          {cap(stale.adjusted).map((r) => (
            <span class="st-diff-chip" key={r.box_id}>{r.product_code} · thùng {r.box_code}: {soVN(r.expected)} → <b>{soVN(r.current)}</b></span>
          ))}
          {stale.adjusted.length > 6 && <span class="st-diff-chip more">+{stale.adjusted.length - 6} thùng</span>}
        </div>
      )}
      {stale.added.length > 0 && (
        <div><span class="st-diff-tag add">Thùng mới</span>
          {cap(stale.added).map((r) => (
            <span class="st-diff-chip" key={r.box_id}>{r.product_code} · thùng {r.box_code}: <b>{soVN(r.remaining)}</b></span>
          ))}
          {stale.added.length > 6 && <span class="st-diff-chip more">+{stale.added.length - 6} thùng</span>}
        </div>
      )}
      {stale.removed.length > 0 && (
        <div><span class="st-diff-tag rem">Đã rời</span>
          {cap(stale.removed).map((r) => (
            <span class="st-diff-chip" key={r.box_id}>{r.product_code} · thùng {r.box_code}</span>
          ))}
          {stale.removed.length > 6 && <span class="st-diff-chip more">+{stale.removed.length - 6} thùng</span>}
        </div>
      )}
    </div>
  );
}

function StocktakeRow({ item, value, bulkVal, looseVal, note, readonly, onValue, onRaw, onNote }:
  { item: StocktakeItem; value: string; bulkVal: string; looseVal: string; note: string; readonly: boolean;
    onValue: (v: string) => void; onRaw: (nb: string, nl: string) => void; onNote: (v: string) => void }) {
  const actual = num(value);
  const diff = actual == null ? null : actual - item.expected_quantity;
  const state = diff == null ? "pending" : Math.abs(diff) <= 1e-9 ? "ok" : diff > 0 ? "plus" : "minus";
  // Vai 📋: bắt đếm bằng đơn vị kiểm → nhập kép [N kiện] + [M lẻ]; sổ sách hiện cùng hệ
  const f = item.count_unit_factor || 0;
  const dual = f > 0;
  const dualText = (total: number) => {
    const b = Math.floor(total / f + 1e-9);
    const l = Math.round((total - b * f) * 1e6) / 1e6;
    return `${soVN(b)} ${item.count_unit_name}${l ? ` + ${soVN(l)} ${item.product_unit || "lẻ"}` : ""}`;
  };
  const fillFull = () => {
    if (!dual) { onValue(String(item.expected_quantity)); return; }
    const b = Math.floor(item.expected_quantity / f + 1e-9);
    const l = Math.round((item.expected_quantity - b * f) * 1e6) / 1e6;
    onRaw(String(b), String(l));
  };
  return (
    <article class={`stocktake-row ${state}`}>
      <div class="stocktake-box-tile box-tile-grid-dense">
        <BoxTile box={{
          id: item.box_id,
          productCode: item.product_code,
          boxCode: item.box_code,
          quantity: item.expected_quantity,
          remaining: item.expected_quantity,
          productUnit: item.product_unit || undefined,
          href: `#/thung/${item.box_id}`,
          title: `${item.product_code} · thùng ${item.box_code} · sổ sách ${soVN(item.expected_quantity)} ${item.product_unit || ""}`,
        }} size="dense" showProductCode />
      </div>
      <div class="stocktake-book">
        <span>Sổ sách</span><b>{soVN(item.expected_quantity)}</b><small>{item.product_unit || ""}</small>
        {dual && <em class="st-book-dual">= {dualText(item.expected_quantity)}</em>}
      </div>
      <div class="stocktake-actual">
        <label>Thực tế{dual ? ` (đếm theo ${item.count_unit_name})` : ""}</label>
        {readonly
          ? <b>{actual == null ? "—" : soVN(actual)}{dual && actual != null && (item.counted_bulk != null || item.counted_loose != null)
              ? <small class="st-book-dual"> ({soVN(item.counted_bulk || 0)} {item.count_unit_name} + {soVN(item.counted_loose || 0)})</small> : null}</b>
          : dual ? (
            <span class="st-dual">
              <input type="number" min="0" step="any" inputMode="numeric" value={bulkVal}
                placeholder="0" onFocus={(e: any) => { const i = e.currentTarget; requestAnimationFrame(() => i.select()); }}
                onInput={(e: any) => onRaw(e.target.value, looseVal)} />
              <small>{item.count_unit_name}</small>
              <span class="st-dual-plus">+</span>
              <input type="number" min="0" step="any" inputMode="decimal" value={looseVal}
                placeholder="0" onFocus={(e: any) => { const i = e.currentTarget; requestAnimationFrame(() => i.select()); }}
                onInput={(e: any) => onRaw(bulkVal, e.target.value)} />
              <small>{item.product_unit || "lẻ"}</small>
            </span>
          )
          : <input type="number" min="0" step="any" inputMode="decimal" value={value}
              placeholder="—" onFocus={(e: any) => {
                const input = e.currentTarget;
                requestAnimationFrame(() => input.select());
              }} onInput={(e: any) => onValue(e.target.value)} />}
        {!readonly && dual && actual != null && (
          <em class="st-book-dual">= {soVN(actual)} {item.product_unit || ""}</em>
        )}
        {!readonly && (
          <span class="stocktake-line-actions">
            <button type="button" title="Xóa số thực tế" disabled={value === ""}
              onClick={() => dual ? onRaw("", "") : onValue("")}>
              <Icon name="close" size={10} /> Xóa
            </button>
            <button type="button" title="Nhập đủ bằng số sổ sách" onClick={fillFull}>
              <Icon name="check" size={10} /> Đủ
            </button>
          </span>
        )}
      </div>
      <div class={`stocktake-row-diff ${state}`}>
        <span>Lệch</span><b>{diff == null ? "—" : signed(diff)}</b>
      </div>
      {(readonly ? !!note : actual != null && Math.abs(diff || 0) > 1e-9) && (
        <div class="stocktake-item-note">
          {readonly ? <span>{note}</span> : <input placeholder="Ghi chú nguyên nhân lệch…" value={note} onInput={(e: any) => onNote(e.target.value)} />}
        </div>
      )}
    </article>
  );
}
