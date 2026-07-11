// Chuyển kho HÀNG LOẠT (#/chuyen-kho): chọn kho NGUỒN → chọn nhiều THÙNG → chọn kho ĐÍCH
// → chuyển. Chỉ thùng còn hàng (không vô hiệu). Data: listPlaces + allBoxes; POST bulkMove.
// Vào từ nút "Chuyển kho" ở dashboard Kho (#/kho).
import { useEffect, useMemo, useState } from "preact/hooks";
import { listPlaces, allBoxes, bulkMove, soVN, type Place, type KhoBox } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";
import { SearchBar } from "../ui/SearchBar";
import { foldVN } from "../format";

const movable = (b: KhoBox) => !b.disabled && (b.remaining ?? b.quantity ?? 0) > 0;

export function BulkMove() {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [boxes, setBoxes] = useState<KhoBox[]>([]);
  const [err, setErr] = useState("");
  const [src, setSrc] = useState<number | null>(null);
  const [dst, setDst] = useState<number | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [qSrc, setQSrc] = useState("");   // lọc kho nguồn
  const [qBox, setQBox] = useState("");   // lọc thùng
  const [qDst, setQDst] = useState("");   // lọc kho đích

  const load = async () => {
    try { const [pl, bx] = await Promise.all([listPlaces(), allBoxes()]); setPlaces(pl); setBoxes(bx); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải kho"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => { if (e.type === "resync" || e.type === "box_changed" || e.type === "inventory_changed") load(); }), []);

  const countAt = (pid: number) => boxes.filter((b) => b.place_id === pid && movable(b)).length;
  const srcBoxes = useMemo(() => src == null ? [] : boxes.filter((b) => b.place_id === src && movable(b))
    .sort((a, b) => (a.product_code || "").localeCompare(b.product_code || "") || (a.box_code || "").localeCompare(b.box_code || "")), [boxes, src]);

  // lọc không dấu: kho theo tên, thùng theo mã SP / số gọi
  const fPlaces = (list: Place[], q: string) => { const n = foldVN(q.trim()); return n ? list.filter((p) => foldVN(p.name).includes(n)) : list; };
  const shownBoxes = useMemo(() => {
    const n = foldVN(qBox.trim());
    return n ? srcBoxes.filter((b) => foldVN(b.product_code || "").includes(n) || foldVN(b.box_code || "").includes(n)) : srcBoxes;
  }, [srcBoxes, qBox]);

  const pickSrc = (id: number) => { setSrc(id); setSel(new Set()); setQBox(""); if (dst === id) setDst(null); };
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // "Chọn tất cả" thao tác trên các thùng ĐANG HIỆN (đã lọc)
  const allShown = shownBoxes.length > 0 && shownBoxes.every((b) => sel.has(b.id));
  const selectAll = () => setSel((s) => { const n = new Set(s); allShown ? shownBoxes.forEach((b) => n.delete(b.id)) : shownBoxes.forEach((b) => n.add(b.id)); return n; });

  const dstName = places?.find((p) => p.id === dst)?.name || "";
  const doMove = async () => {
    if (!sel.size || dst == null) return;
    if (!(await confirmDialog(`Chuyển ${sel.size} thùng sang "${dstName}"?`, { okLabel: "Chuyển" }))) return;
    setBusy(true);
    try {
      const r = await bulkMove([...sel], dst);
      toast(`Đã chuyển ${r.moved} thùng sang ${r.to_name}${r.skipped ? ` · bỏ qua ${r.skipped}` : ""}`, "ok");
      setSel(new Set()); setDst(null);
      await load();
    } catch (e: any) { toast(e?.message || "Lỗi chuyển kho", "err"); }
    finally { setBusy(false); }
  };

  const head = (
    <div class="bm-head">
      <BackLink fallback="#/kho" />
      <div>
        <div class="bm-title"><Icon name="truck" size={18} /> Chuyển kho hàng loạt</div>
        <div class="muted small">Kho nguồn → chọn thùng → kho đích</div>
      </div>
    </div>
  );
  if (err) return <div class="bm-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!places) return <div class="bm-page">{head}<Loading /></div>;

  return (
    <div class="bm-page">
      {head}

      <div class="bm-step">
        <div class="bm-step-h"><b>1 · Kho nguồn</b></div>
        <SearchBar value={qSrc} onInput={setQSrc} placeholder="Tìm kho nguồn…" />
        <div class="bm-places">
          {fPlaces(places, qSrc).map((p) => (
            <button key={p.id} class={"bm-place" + (src === p.id ? " on" : "")} onClick={() => pickSrc(p.id)}>
              {p.name} <span class="bm-place-n">{countAt(p.id)}</span>
            </button>
          ))}
        </div>
      </div>

      {src != null && (
        <div class="bm-step">
          <div class="bm-step-h">
            <b>2 · Chọn thùng</b> <span class="muted small">(chọn {sel.size}/{srcBoxes.length})</span>
            {shownBoxes.length > 0 && <button class="bm-selall" onClick={selectAll}>{allShown ? "Bỏ chọn" : "Chọn tất cả"}</button>}
          </div>
          <SearchBar value={qBox} onInput={setQBox} placeholder="Tìm mã SP / số thùng…" />
          {srcBoxes.length === 0 ? (
            <p class="muted small">Kho này không có thùng chuyển được.</p>
          ) : shownBoxes.length === 0 ? (
            <p class="muted small">Không có thùng khớp "{qBox}".</p>
          ) : (
            <div class="bm-boxes">
              {shownBoxes.map((b) => {
                const num = (b.box_code || "").split("-").pop() || b.box_code;
                const on = sel.has(b.id);
                return (
                  <button key={b.id} class={"bm-box" + (on ? " on" : "")} onClick={() => toggle(b.id)}>
                    <span class="bm-box-chk">{on && <Icon name="check" size={13} />}</span>
                    <span class="bm-box-code">{b.product_code}</span>
                    <span class="bm-box-num">{num}</span>
                    <span class="bm-box-q muted small">{soVN(b.remaining ?? b.quantity)}{b.product_unit ? ` ${b.product_unit}` : ""}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {sel.size > 0 && (
        <div class="bm-step">
          <div class="bm-step-h"><b>3 · Kho đích</b></div>
          <SearchBar value={qDst} onInput={setQDst} placeholder="Tìm kho đích…" />
          <div class="bm-places">
            {fPlaces(places.filter((p) => p.id !== src), qDst).map((p) => (
              <button key={p.id} class={"bm-place" + (dst === p.id ? " on" : "")} onClick={() => setDst(p.id)}>{p.name}</button>
            ))}
          </div>
        </div>
      )}

      {sel.size > 0 && dst != null && (
        <div class="bm-action">
          <button class="btn primary block" disabled={busy} onClick={doMove}>
            <Icon name="truck" size={16} /> Chuyển {sel.size} thùng → {dstName}
          </button>
        </div>
      )}
    </div>
  );
}
