// Dashboard KHO ĐẬU (#/kho-dau) — tồn đọc được 2 KIỂU: theo LOẠI ĐẬU hoặc theo
// KHO (cùng dữ liệu, đổi trục bằng nút gạt). 3 nút tạo phiếu nhập/xuất/điều chỉnh
// ở trên. Hệ kho RIÊNG, không dính kho hàng hoá. Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { getBeanBoard, soVN, type BeanBoardData } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SearchBar } from "../ui/SearchBar";
import { EmptyState, ErrorState, SkeletonList } from "../ui/states";

let beanCache: BeanBoardData | null = null;
onRealtime((e) => { if (e.type === "bean_changed" || e.type === "resync") beanCache = null; });

type View = "bean" | "place";

export function BeanBoard() {
  const [data, setData] = useState<BeanBoardData | null>(beanCache);
  const [view, setView] = useState<View>(
    (localStorage.getItem("bean_board_view") as View) || "bean");
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");

  const load = () => getBeanBoard()
    .then((d) => { setData(d); beanCache = d; setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải kho đậu"));
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load();
  }), []);
  const setV = (v: View) => { setView(v); localStorage.setItem("bean_board_view", v); };

  if (err && !data) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!data) return <SkeletonList />;

  const placeName = (id: number) => data.places.find((p) => p.id === id)?.name || `Kho #${id}`;
  const beanName = (id: number) => data.beans.find((b) => b.id === id)?.name || `Đậu #${id}`;
  const beanUnit = (id: number) => data.beans.find((b) => b.id === id)?.unit || "";
  const nq = foldVN(q.trim());

  const rows = view === "bean"
    ? data.by_bean.filter((r) => !nq || foldVN(r.name).includes(nq))
    : data.by_place.filter((r) => !nq || foldVN(r.name).includes(nq));

  const noSetup = !data.beans.length || !data.places.length;

  return (
    <div class="bean-board">
      <PageHead fallback="#/home"
        title={<><Icon name="box" size={18} /> Kho đậu</>}
        sub={`${data.beans.length} loại đậu · ${data.places.length} kho · ${data.slip_count} phiếu`}
        right={<a class="btn small" href="#/kho-dau/thiet-lap"><Icon name="settings" size={15} /></a>} />

      <div class="bean-actions">
        <a class="btn primary" href="#/kho-dau/tao?kind=nhap"><Icon name="plus" size={16} /> Nhập</a>
        <a class="btn" href="#/kho-dau/tao?kind=xuat"><Icon name="truck" size={16} /> Xuất</a>
        <a class="btn" href="#/kho-dau/tao?kind=dieu_chinh"><Icon name="edit" size={16} /> Điều chỉnh</a>
      </div>

      {noSetup && (
        <div class="bean-hint">
          Chưa thiết lập xong: cần ít nhất 1 <b>loại đậu</b> và 1 <b>kho</b>.{" "}
          <a href="#/kho-dau/thiet-lap">Thiết lập ngay →</a>
        </div>
      )}

      <div class="bean-total">
        <span class="muted small">Tổng tồn</span>
        <b>{soVN(data.total)}</b>
      </div>

      <div class="seg bean-seg">
        <button class={"seg-btn" + (view === "bean" ? " active" : "")} onClick={() => setV("bean")}>
          Theo loại đậu
        </button>
        <button class={"seg-btn" + (view === "place" ? " active" : "")} onClick={() => setV("place")}>
          Theo kho
        </button>
      </div>

      <SearchBar value={q} onInput={setQ}
        placeholder={view === "bean" ? "Tìm loại đậu…" : "Tìm kho…"} />

      {!rows.length && (
        <EmptyState>
          {nq ? `Không có mục khớp "${q.trim()}".`
              : view === "bean" ? "Chưa có loại đậu nào." : "Chưa có kho nào."}
        </EmptyState>
      )}

      {view === "bean" && rows.map((r: any) => (
        <div class="bean-card" key={r.id}>
          <div class="bean-card-main">
            <div class="bean-card-name">{r.name}</div>
            <div class="bean-card-sub muted small">
              {r.places.length
                ? r.places.map((p: any) => `${placeName(p.place_id)}: ${soVN(p.qty)}`).join(" · ")
                : "chưa có tồn ở kho nào"}
            </div>
          </div>
          <div class="bean-card-stat">
            <span class={"bean-qty" + (r.total > 0 ? "" : " zero")}>{soVN(r.total)}</span>
            <span class="muted small">{r.unit}</span>
          </div>
        </div>
      ))}

      {view === "place" && rows.map((r: any) => (
        <div class="bean-card" key={r.id}>
          <div class="bean-card-main">
            <div class="bean-card-name"><Icon name="box" size={14} /> {r.name}</div>
            <div class="bean-card-sub muted small">
              {r.beans.length
                ? r.beans.map((b: any) => `${beanName(b.bean_id)}: ${soVN(b.qty)} ${beanUnit(b.bean_id)}`).join(" · ")
                : "kho trống"}
            </div>
          </div>
          <div class="bean-card-stat">
            <span class={"bean-qty" + (r.total > 0 ? "" : " zero")}>{soVN(r.total)}</span>
            <span class="muted small">{r.beans.length} loại</span>
          </div>
        </div>
      ))}

      <a class="btn bean-more" href="#/kho-dau/phieu">
        <Icon name="receipt" size={15} /> Phiếu nhập / xuất / điều chỉnh
      </a>
    </div>
  );
}
