// Popup soạn hàng — bấm "Xong" ở task Soạn hàng.
// - Đơn ĐÃ CÓ ảnh gắn loại "soạn hàng" → hiện thẳng để XÁC NHẬN (không bắt chọn tay).
// - Chưa có ảnh soạn hàng → chọn ≥1 ảnh từ POOL ảnh của đơn (như cũ).
// Lưu id ảnh đã dùng vào note task (imgs:<id,id>). Data: GET /api/order/{id}/images,
// POST /api/order/task.
import { useEffect, useState } from "preact/hooks";
import { listMediaImages, mediaImageUrl, postJSON, type OrderImage } from "../api";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { kindOf } from "./imageKinds";
import { fastScrollToEl } from "../scroll";

export function SoanHangPicker({ threadId, onClose, onDone }: { threadId: string; onClose: () => void; onDone: () => void }) {
  usePopupBack(true, onClose);   // back → đóng popup trước
  const base = `/api/order/${threadId}`;
  const [images, setImages] = useState<OrderImage[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [manual, setManual] = useState(false);   // ép chọn tay dù đã có ảnh soạn hàng
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listMediaImages(base).then(setImages).catch(() => setImages([]));
  }, [base]);

  const soanImgs = (images || []).filter((x) => kindOf(x) === "soan_hang");
  // Chế độ xác nhận: có ảnh soạn hàng sẵn + chưa ép chọn tay
  const confirmMode = soanImgs.length > 0 && !manual;

  const toggle = (id: number) => setSel((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const save = async (ids: number[]) => {
    if (!ids.length) return;
    setBusy(true);
    try {
      await postJSON("/api/order/task", { thread_id: Number(threadId), type: "soan_hang", note: `imgs:${ids.join(",")}`, done: true });
      toast(`✅ Soạn hàng · ${ids.length} ảnh`, "ok");
      onDone();
      onClose();
    } catch (e: any) {
      toast(e?.message || "Lỗi ghi soạn hàng", "err");
      setBusy(false);
    }
  };

  const goAddPhoto = () => { onClose(); const el = document.getElementById("od-camera"); if (el) fastScrollToEl(el, "start"); };

  return (
    <div class="modal-overlay" onClick={busy ? undefined : onClose}>
      <div class="modal-sheet sh-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="box" size={18} /> {confirmMode ? "Xác nhận soạn hàng" : "Chọn ảnh soạn hàng"} {busy && "· ⏳"}</div>

        {images === null ? (
          <p class="muted small">Đang tải ảnh…</p>
        ) : confirmMode ? (
          <>
            <p class="muted small">Xác nhận những hình ảnh sau đây của soạn hàng:</p>
            <div class="sh-grid">
              {soanImgs.map((img) => (
                <div class="sh-tile on static" key={img.id}>
                  <img src={mediaImageUrl(base, img.id, "thumb")} loading="lazy" alt="" />
                </div>
              ))}
            </div>
            <button class="btn primary block" disabled={busy} onClick={() => save(soanImgs.map((x) => x.id))}>
              {busy ? "⏳ Đang lưu…" : `✅ Xác nhận (${soanImgs.length} ảnh)`}
            </button>
            <button class="btn block" disabled={busy} onClick={() => { setManual(true); setSel(new Set(soanImgs.map((x) => x.id))); }}>Chọn ảnh khác</button>
          </>
        ) : images.length === 0 ? (
          <>
            <p class="sh-empty">⚠️ Đơn chưa có ảnh. Phải thêm ảnh trước khi soạn xong.</p>
            <button class="btn primary block" onClick={goAddPhoto}><Icon name="camera" size={16} /> Thêm ảnh cho đơn</button>
          </>
        ) : (
          <>
            <p class="muted small">Chọn ảnh dùng cho soạn hàng (≥1).</p>
            <div class="sh-grid">
              {images.map((img) => (
                <button
                  class={"sh-tile" + (sel.has(img.id) ? " on" : "")}
                  key={img.id}
                  disabled={busy}
                  onClick={() => toggle(img.id)}
                >
                  <img src={mediaImageUrl(base, img.id, "thumb")} loading="lazy" alt="" />
                  {sel.has(img.id) && <span class="sh-check">✓</span>}
                </button>
              ))}
            </div>
            <button class="btn primary block" disabled={busy || !sel.size} onClick={() => save([...sel])}>
              {busy ? "⏳ Đang lưu…" : `✅ Xong (${sel.size} ảnh)`}
            </button>
          </>
        )}

        {!busy && <button class="btn sh-cancel" onClick={onClose}>Huỷ</button>}
      </div>
    </div>
  );
}
