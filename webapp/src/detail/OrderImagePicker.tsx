// Chọn MỘT ảnh tham chiếu từ pool ảnh sẵn có của đơn — không upload ảnh mới.
import { useEffect, useState } from "preact/hooks";
import { listOrderImages, orderImageUrl, type OrderImage } from "../api";
import { Icon } from "../ui/Icon";
import { LoadingInline } from "../ui/states";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { KIND_ICON, KIND_LABEL, kindOf } from "./imageKinds";

export function OrderImagePicker({ threadId, selectedId, onPick, onClose }: {
  threadId: string;
  selectedId?: number;
  onPick: (image: OrderImage) => void;
  onClose: () => void;
}) {
  const [images, setImages] = useState<OrderImage[] | null>(null);
  const [failed, setFailed] = useState(false);
  usePopupBack(true, onClose);
  useScrollLock(true);   // khoá cuộn nền khi popup mở

  const load = () => {
    setImages(null);
    setFailed(false);
    listOrderImages(threadId)
      .then((rows) => setImages(rows.filter((image) => !image.deleted_at)))
      .catch(() => { setImages([]); setFailed(true); });
  };
  useEffect(load, [threadId]);

  return (
    <div class="modal-overlay" onClick={onClose}>
      <div class="modal-sheet sh-sheet refimg-sheet" role="dialog" aria-modal="true"
        aria-label="Chọn ảnh tham chiếu" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head">
          <Icon name="image" size={18} /> Chọn ảnh của đơn
        </div>

        {images === null ? (
          <p class="muted small"><LoadingInline label="Đang tải ảnh…" /></p>
        ) : failed ? (
          <>
            <p class="sh-empty">Không tải được ảnh của đơn.</p>
            <button class="btn block" onClick={load}><Icon name="refresh" size={16} /> Thử lại</button>
          </>
        ) : images.length === 0 ? (
          <p class="sh-empty">Đơn chưa có ảnh. Hãy thêm ảnh ở trang chi tiết đơn trước.</p>
        ) : (
          <>
            <p class="muted small">Chạm một ảnh để dùng làm ảnh đối chiếu khi sửa hóa đơn.</p>
            <div class="sh-grid refimg-grid">
              {images.map((image) => {
                const kind = kindOf(image);
                const selected = image.id === selectedId;
                return (
                  <button class={"sh-tile refimg-tile" + (selected ? " on" : "")} key={image.id}
                    aria-pressed={selected} aria-label={`Chọn ảnh ${KIND_LABEL[kind]}`}
                    onClick={() => onPick(image)}>
                    <img src={orderImageUrl(threadId, image.id, "thumb")} loading="lazy" alt="" />
                    <span class="refimg-kind">{KIND_ICON[kind]} {KIND_LABEL[kind]}</span>
                    {selected && <span class="sh-check">✓</span>}
                  </button>
                );
              })}
            </div>
          </>
        )}

        <button class="btn sh-cancel" onClick={onClose}>Huỷ</button>
      </div>
    </div>
  );
}
