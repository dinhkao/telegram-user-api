import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  completeStocktake, getStocktake, isOffice, lockStocktake, resyncStocktake, saveStocktake,
  soVN, unlockStocktake, voidStocktake,
  type Stocktake, type StocktakeItem,
} from "../api";
import { foldVN, fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { BoxTile } from "../detail/BoxTile";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";
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
  const latestRef = useRef<{ counts: { id: number; actual_quantity: number | null; note?: string }[]; note: string }>({ counts: [], note: "" });

  const adopt = (d: Stocktake) => {
    setSlip(d);
    setValues(Object.fromEntries(d.items.map((it) => [it.id, it.actual_quantity == null ? "" : String(it.actual_quantity)])));
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
      let counted = 0, deviations = 0;
      for (const it of all) {
        const actual = num(values[it.id] ?? "");
        if (actual == null || !Number.isFinite(actual)) continue;
        counted += 1;
        if (Math.abs(actual - it.expected_quantity) > 1e-9) deviations += 1;
      }
      return { code, items, counted, total: all.length, deviations, unit: all[0]?.product_unit || "" };
    });
  }, [slip, visible, values]);

  const counts = () => (slip?.items || []).map((it) => ({
    id: it.id,
    actual_quantity: num(values[it.id] ?? ""),
    note: notes[it.id] || "",
  }));
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
    } catch (e: any) {
      toast(e?.message || "Lỗi hoàn tất phiếu", "err");
      reloadStale();   // có thể bị chặn vì kho vừa biến động → hiện banner cảnh báo
    }
    finally { setBusy(false); }
  };
  const fillMatched = () => {
    if (!slip) return;
    setValues((old) => ({ ...old, ...Object.fromEntries(slip.items.map((it) => [it.id, old[it.id] === "" || old[it.id] == null ? String(it.expected_quantity) : old[it.id]])) }));
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
      <div class="prod-detail-head">
        <BackLink fallback={`#/vi-tri/${slip.place_id}`} />
        <div class="stocktake-title">
          <div class="prod-sp big"><Icon name="clipboard" size={18} /> Phiếu kiểm kho #{slip.id}</div>
          <div class="prod-date muted">{slip.place_name} · chụp lúc {fmtDateTimeVN(slip.captured_at)}</div>
        </div>
        <span class={`stocktake-status ${done ? "done" : voided ? "voided" : lockState}`}>
          {done ? "Đã chốt" : voided ? "Đã huỷ" : lockState === "mine" ? "Bạn đang kiểm" : lockState === "other" ? `${holder} đang kiểm` : "Đang xin quyền…"}
        </span>
      </div>

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
          <input class="inv-search" placeholder="Tìm mã SP hoặc số thùng…" value={q} onInput={(e: any) => setQ(e.target.value)} />
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
            <div class="stocktake-list">
              {group.items.map((it) => <StocktakeRow key={it.id} item={it} value={values[it.id] ?? ""} note={notes[it.id] || ""}
                readonly={readOnly} onValue={(v) => { setValues((old) => ({ ...old, [it.id]: v })); markDirty(); }}
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

function StocktakeRow({ item, value, note, readonly, onValue, onNote }:
  { item: StocktakeItem; value: string; note: string; readonly: boolean; onValue: (v: string) => void; onNote: (v: string) => void }) {
  const actual = num(value);
  const diff = actual == null ? null : actual - item.expected_quantity;
  const state = diff == null ? "pending" : Math.abs(diff) <= 1e-9 ? "ok" : diff > 0 ? "plus" : "minus";
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
      </div>
      <div class="stocktake-actual">
        <label>Thực tế</label>
        {readonly
          ? <b>{actual == null ? "—" : soVN(actual)}</b>
          : <input type="number" min="0" step="any" inputMode="decimal" value={value}
              placeholder="—" onFocus={(e: any) => {
                const input = e.currentTarget;
                requestAnimationFrame(() => input.select());
              }} onInput={(e: any) => onValue(e.target.value)} />}
        {!readonly && (
          <span class="stocktake-line-actions">
            <button type="button" title="Xóa số thực tế" disabled={value === ""} onClick={() => onValue("")}>
              <Icon name="close" size={10} /> Xóa
            </button>
            <button type="button" title="Nhập đủ bằng số sổ sách" onClick={() => onValue(String(item.expected_quantity))}>
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
