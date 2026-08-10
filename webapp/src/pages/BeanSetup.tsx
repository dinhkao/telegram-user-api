// THIẾT LẬP KHO ĐẬU (#/kho-dau/thiet-lap) — 2 danh mục: VỊ TRÍ KHO (Kho A, Kho B…)
// và LOẠI ĐẬU (tên + đơn vị chính). Thêm = nút mở POPUP (detail/BeanAddPopup); quy
// đổi đơn vị = nút ⇄ mở POPUP (detail/BeanUnits). SỬA/XOÁ nằm ở TRANG CHI TIẾT
// (#/kho-dau/dau/:id, #/kho-dau/kho/:id) — bấm vào dòng để mở, ở đây chỉ liệt kê.
// Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { getBeanBoard, soVN, type BeanBoardData } from "../api";
import { BeanAddPopup, type BeanAddMode } from "../detail/BeanAddPopup";
import { BeanUnits } from "../detail/BeanUnits";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { ErrorState, SkeletonList } from "../ui/states";

export function BeanSetup() {
  const [data, setData] = useState<BeanBoardData | null>(null);
  const [err, setErr] = useState("");
  const [adding, setAdding] = useState<BeanAddMode | null>(null);   // popup thêm kho / loại đậu
  const [unitsFor, setUnitsFor] = useState<number | null>(null);    // popup quy đổi đơn vị

  const load = () => getBeanBoard()
    .then((d) => { setData(d); setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải kho đậu"));
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load();
  }), []);

  if (err && !data) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!data) return <SkeletonList />;

  const beanTotal = (id: number) => data.by_bean.find((b) => b.id === id)?.total || 0;
  const placeTotal = (id: number) => data.by_place.find((p) => p.id === id)?.total || 0;
  // Lấy lại từ data mỗi lần render → popup luôn thấy đơn vị mới nhất sau khi sửa.
  const unitsBean = data.beans.find((b) => b.id === unitsFor);

  return (
    <div class="bean-setup">
      <PageHead fallback="#/kho-dau" title={<><Icon name="settings" size={18} /> Thiết lập kho đậu</>}
        sub="Vị trí kho + danh mục đậu" />

      <div class="ie-head">
        Vị trí kho ({data.places.length})
        <button class="btn small primary bean-head-add" onClick={() => setAdding("place")}>
          <Icon name="plus" size={14} /> Thêm kho
        </button>
      </div>
      {!data.places.length && <p class="muted small">Chưa có kho nào — bấm "Thêm kho" để tạo Kho A, Kho B…</p>}
      {data.places.map((p) => (
        <a class="bean-row" href={`#/kho-dau/kho/${p.id}`} key={p.id}>
          <div class="bean-row-main">
            <div class="bean-row-name"><Icon name="box" size={14} /> {p.name}</div>
            <div class="muted small">tồn {soVN(placeTotal(p.id))}{p.note ? ` · ${p.note}` : ""}</div>
          </div>
          <Icon name="chevronRight" size={18} class="kg-arrow" />
        </a>
      ))}

      <div class="ie-head">
        Danh mục đậu ({data.beans.length})
        <button class="btn small primary bean-head-add" onClick={() => setAdding("bean")}>
          <Icon name="plus" size={14} /> Thêm loại đậu
        </button>
      </div>
      {!data.beans.length && <p class="muted small">Chưa có loại đậu nào.</p>}
      {data.beans.map((b) => (
        <div class="bean-row" key={b.id}>
          {/* Bấm dòng → trang chi tiết (sửa/xoá ở đó); nút ⇄ nằm NGOÀI link để bấm
              không nhảy trang. */}
          <a class="bean-row-main" href={`#/kho-dau/dau/${b.id}`}>
            <div class="bean-row-name">{b.name}</div>
            <div class="muted small">tồn {soVN(beanTotal(b.id))} {b.unit}</div>
          </a>
          <button class="btn small" title="Quy đổi đơn vị" onClick={() => setUnitsFor(b.id)}>
            ⇄ {(b.units || []).length || ""}
          </button>
          <a class="bean-row-go" href={`#/kho-dau/dau/${b.id}`} aria-label="Mở chi tiết">
            <Icon name="chevronRight" size={18} class="kg-arrow" />
          </a>
        </div>
      ))}

      <p class="muted small bean-hint-foot">
        Bấm vào dòng để mở chi tiết — sửa tên, ghi chú, xoá đều ở đó.
        Nút ⇄ = khai đơn vị quy đổi (1 bao = 50 kg…) và đổi đơn vị chính.
      </p>

      {adding && <BeanAddPopup mode={adding} onClose={() => setAdding(null)} onDone={load} />}
      {unitsBean && (
        <BeanUnits bean={unitsBean} onClose={() => setUnitsFor(null)} onChanged={load} />
      )}
    </div>
  );
}
