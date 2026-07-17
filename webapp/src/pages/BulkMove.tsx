// Chuyển kho HÀNG LOẠT (#/chuyen-kho): chọn kho NGUỒN → chọn nhiều THÙNG → chọn kho ĐÍCH
// → chuyển. Chỉ thùng còn hàng (không vô hiệu). Data: listPlaces + allBoxes; POST bulkMove.
// Vào từ nút "Chuyển kho" ở dashboard Kho (#/kho).
import { useEffect, useMemo, useState } from "preact/hooks";
import { listPlaces, allBoxes, bulkMove, type Place, type KhoBox } from "../api";
import { onRealtime } from "../realtime";
import { PageHead } from "../ui/PageHead";
import { Icon } from "../ui/Icon";
import { Loading, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";
import { foldVN } from "../format";
import { MoveBoxesStep, MoveDestinationStep, MoveSourceStep, movable, type MoveSource } from "./BulkMoveSteps";

export function BulkMove() {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [boxes, setBoxes] = useState<KhoBox[]>([]);
  const [err, setErr] = useState("");
  const [src, setSrc] = useState<MoveSource | null>(null);
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

  const srcBoxes = useMemo(() => src == null ? [] : boxes.filter((b) =>
    (src === "unplaced" ? b.place_id == null : b.place_id === src) && movable(b))
    .sort((a, b) => a.id - b.id), [boxes, src]);

  const shownBoxes = useMemo(() => {
    const n = foldVN(qBox.trim());
    return n ? srcBoxes.filter((b) => foldVN(b.product_code || "").includes(n) || foldVN(b.box_code || "").includes(n)) : srcBoxes;
  }, [srcBoxes, qBox]);

  const pickSrc = (source: MoveSource) => {
    setSrc(source); setSel(new Set()); setQBox("");
    if (typeof source === "number" && dst === source) setDst(null);
  };
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
    <PageHead fallback="#/kho"
      title={<><Icon name="truck" size={18} /> Chuyển kho hàng loạt</>}
      sub="Kho nguồn → chọn thùng → kho đích" />
  );
  if (err) return <div class="bm-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!places) return <div class="bm-page">{head}<Loading /></div>;

  return (
    <div class="bm-page">
      {head}

      <MoveSourceStep places={places} boxes={boxes} value={src} query={qSrc} onQuery={setQSrc} onPick={pickSrc} />

      {src != null && <MoveBoxesStep boxes={shownBoxes} total={srcBoxes.length} selected={sel} query={qBox} allShown={allShown}
        onQuery={setQBox} onToggle={toggle} onSelectAll={selectAll} />}

      {sel.size > 0 && src != null && <MoveDestinationStep places={places} source={src} value={dst}
        query={qDst} onQuery={setQDst} onPick={setDst} />}

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
