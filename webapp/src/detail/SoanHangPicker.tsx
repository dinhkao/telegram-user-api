// Popup chọn ảnh soạn hàng — bấm "Xong" ở task Soạn hàng phải chọn ≥1 ảnh từ POOL
// ảnh sẵn có của đơn. Không có ảnh → KHÔNG soạn xong được. Lưu id ảnh đã chọn vào
// note task (imgs:<id,id>). Data: GET /api/order/{id}/images, POST /api/order/task.
import { useEffect, useState } from "preact/hooks";
import { listMediaImages, mediaImageUrl, postJSON, type OrderImage } from "../api";
import { toast } from "../ui/feedback";

export function SoanHangPicker({ threadId, onClose, onDone }: { threadId: string; onClose: () => void; onDone: () => void }) {
  const base = `/api/order/${threadId}`;
  const [images, setImages] = useState<OrderImage[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listMediaImages(base).then(setImages).catch(() => setImages([]));
  }, [base]);

  const toggle = (id: number) => setSel((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const confirm = async () => {
    if (!sel.size) return;
    setBusy(true);
    try {
      const note = `imgs:${[...sel].join(",")}`;
      await postJSON("/api/order/task", { thread_id: Number(threadId), type: "soan_hang", note, done: true });
      toast(`✅ Soạn hàng · ${sel.size} ảnh`, "ok");
      onDone();
      onClose();
    } catch (e: any) {
      toast(e?.message || "Lỗi ghi soạn hàng", "err");
      setBusy(false);
    }
  };

  const goAddPhoto = () => { onClose(); document.getElementById("od-camera")?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  return (
    <div class="modal-overlay" onClick={busy ? undefined : onClose}>
      <div class="modal-sheet sh-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head">📦 Chọn ảnh soạn hàng {busy && "· ⏳"}</div>

        {images === null ? (
          <p class="muted small">Đang tải ảnh…</p>
        ) : images.length === 0 ? (
          <>
            <p class="sh-empty">⚠️ Đơn chưa có ảnh. Phải thêm ảnh trước khi soạn xong.</p>
            <button class="btn primary block" onClick={goAddPhoto}>📷 Thêm ảnh cho đơn</button>
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
            <button class="btn primary block" disabled={busy || !sel.size} onClick={confirm}>
              {busy ? "⏳ Đang lưu…" : `✅ Xong (${sel.size} ảnh)`}
            </button>
          </>
        )}

        {!busy && <button class="btn sh-cancel" onClick={onClose}>Huỷ</button>}
      </div>
    </div>
  );
}
