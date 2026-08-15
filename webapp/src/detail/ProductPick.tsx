// CHỌN SẢN PHẨM đang chụp mâm — dùng ở bảng #/chat-luong và trang chi tiết thợ.
// Ảnh chụp SAU khi chọn sẽ được gắn mã SP này (gửi kèm field `product` lúc upload).
//
// Lựa chọn nhớ theo MÁY (localStorage), KHÔNG lưu server: nhiều người có thể đang
// sửa hai loại kẹo khác nhau cùng lúc — nếu lưu chung, người này đổi SP sẽ âm thầm
// gắn nhầm sản phẩm cho ảnh của người kia. Mỗi máy tự chọn, và chọn gì thì hiện
// rõ ngay trên nút để không chụp nhầm.
// Data: listQualityProducts (nằm dưới /api/quality nên vai trò chat_luong gọi được).
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { listQualityProducts } from "../api";
import { foldVN } from "../format";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";
import { Loading } from "../ui/states";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";

const KEY = "quality_product";

export function readProduct(): string {
  try { return localStorage.getItem(KEY) || ""; } catch { return ""; }
}
export function saveProduct(code: string) {
  try { code ? localStorage.setItem(KEY, code) : localStorage.removeItem(KEY); }
  catch { /* trình duyệt chặn/đầy — vẫn chạy, chỉ không nhớ được */ }
}

/** Nút hiện SP đang chọn; bấm mở popup đổi. */
export function ProductPick({ value, onChange, compact }: {
  value: string;
  onChange: (code: string) => void;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button class={"btn small qp-btn" + (value ? " on" : "")} onClick={() => setOpen(true)}
        title="Chọn sản phẩm sẽ gắn cho ảnh chụp sau đó">
        <Icon name="tag" size={15} />
        {value ? <b>{value}</b> : (compact ? "Chọn SP" : "Chưa chọn sản phẩm")}
      </button>
      {open && (
        <ProductPopup value={value}
          onClose={() => setOpen(false)}
          onPick={(c) => { onChange(c); setOpen(false); }} />
      )}
    </>
  );
}

function ProductPopup({ value, onPick, onClose }: {
  value: string;
  onPick: (code: string) => void;
  onClose: () => void;
}) {
  const [all, setAll] = useState<{ code: string; name: string }[] | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const inp = useRef<HTMLInputElement>(null);
  useScrollLock(true);
  usePopupBack(true, onClose);

  useEffect(() => {
    listQualityProducts()
      .then((d) => { setAll(d.products); setRecent(d.recent); })
      .catch(() => setAll([]));
  }, []);

  const nq = foldVN(q.trim());
  const shown = (all || []).filter((p) =>
    !nq || foldVN(p.code).includes(nq) || foldVN(p.name).includes(nq));
  // Đang tìm thì hiện đúng kết quả tìm; không tìm thì tách khối "Dùng gần đây"
  // lên đầu (mã của cả xưởng, do server tính) rồi mới tới danh mục đầy đủ.
  const byCode = new Map(shown.map((p) => [p.code, p]));
  const recentRows = nq ? [] : recent.map((c) => byCode.get(c)).filter(Boolean) as
    { code: string; name: string }[];
  const restRows = recentRows.length
    ? shown.filter((p) => !recent.includes(p.code)) : shown;

  return createPortal(
    <div class="cam-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="qb-set">
        <div class="row space qb-set-head">
          <b><Icon name="tag" size={16} /> Sản phẩm đang chụp</b>
          <button class="prv-x" onClick={onClose} title="Đóng"><Icon name="close" size={20} /></button>
        </div>
        <p class="muted small qb-set-hint">
          Ảnh chụp <b>sau khi chọn</b> sẽ được gắn sản phẩm này. Nhớ riêng trên máy này.
        </p>
        <div style={{ padding: "0 12px" }}>
          <SearchBar value={q} onInput={setQ} placeholder="Tìm mã hoặc tên sản phẩm…" />
        </div>

        <div class="qb-set-list">
          {all === null ? <Loading /> : (
            <>
              <button class={"qp-item" + (value ? "" : " on")} onClick={() => onPick("")}>
                <span class="muted">— Không gắn sản phẩm —</span>
              </button>
              {recentRows.length > 0 && (
                <>
                  <div class="qp-sec muted small">Dùng gần đây</div>
                  {recentRows.map((p) => (
                    <button class={"qp-item" + (p.code === value ? " on" : "")} key={"r-" + p.code}
                      onClick={() => onPick(p.code)}>
                      <b>{p.code}</b>{p.name ? <span class="muted"> · {p.name}</span> : null}
                    </button>
                  ))}
                  <div class="qp-sec muted small">Tất cả sản phẩm</div>
                </>
              )}
              {restRows.map((p) => (
                <button class={"qp-item" + (p.code === value ? " on" : "")} key={p.code}
                  onClick={() => onPick(p.code)}>
                  <b>{p.code}</b>{p.name ? <span class="muted"> · {p.name}</span> : null}
                </button>
              ))}
              {shown.length === 0 && <p class="muted small">Không có SP khớp "{q.trim()}".</p>}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
