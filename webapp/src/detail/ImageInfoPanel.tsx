// Bảng thông tin 1 ảnh trong trình xem (PhotoViewer): đổi LOẠI + BÌNH LUẬN ảnh.
// Chỉ dùng cho ảnh đơn hàng (base = /api/order/<id>). Data: {base}/images/{id}/kind
// + {base}/images/{id}/comments. Tách khỏi PhotoViewer để giữ file ≤400 dòng.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  addImageComment, deleteImageComment, listImageComments, setImageKind,
  type ImageComment, type OrderImage,
} from "../api";
import { KIND_ORDER, KIND_LABEL, KIND_ICON, kindOf } from "./imageKinds";
import { fmtRelative } from "../format";
import { toast, confirmDialog } from "../ui/feedback";
import { Icon } from "../ui/Icon";

export function ImageInfoPanel({
  base, image, onKindChange,
}: {
  base: string;
  image: OrderImage;
  onKindChange?: (id: number, kind: string) => void;
}) {
  const [kind, setKind] = useState<string>(kindOf(image));
  const [comments, setComments] = useState<ImageComment[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Đổi ảnh → nạp lại loại + bình luận của ảnh đang xem
  useEffect(() => {
    setKind(kindOf(image));
    setComments([]);
    let alive = true;
    listImageComments(base, image.id).then((c) => { if (alive) setComments(c); }).catch(() => {});
    return () => { alive = false; };
  }, [base, image.id]);

  const changeKind = async (k: string) => {
    if (k === kind) return;
    const prev = kind;
    setKind(k);                     // lạc quan
    onKindChange?.(image.id, k);
    try {
      await setImageKind(base, image.id, k);
    } catch (e: any) {
      setKind(prev);
      onKindChange?.(image.id, prev);
      toast(e?.message || "Đổi loại thất bại");
    }
  };

  const add = async () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    try {
      const c = await addImageComment(base, image.id, t);
      setComments((prev) => [...prev, c]);
      setText("");
      taRef.current?.focus();
    } catch (e: any) {
      toast(e?.message || "Gửi bình luận thất bại");
    } finally {
      setBusy(false);
    }
  };

  const del = async (c: ImageComment) => {
    if (!(await confirmDialog("Xoá bình luận này?", { danger: true }))) return;
    setComments((prev) => prev.filter((x) => x.id !== c.id));  // lạc quan
    try {
      await deleteImageComment(base, image.id, c.id);
    } catch {
      setComments((prev) => [...prev, c].sort((a, b) => a.created_at - b.created_at));
    }
  };

  return (
    <div class="pv-panel">
      <div class="pv-kind">
        <span class="muted small">Loại:</span>
        {KIND_ORDER.map((k) => (
          <button key={k} class={"kchip" + (kind === k ? " on" : "")} onClick={() => changeKind(k)}>
            {KIND_ICON[k]} {KIND_LABEL[k]}
          </button>
        ))}
      </div>

      <div class="pv-cmts">
        {comments.length === 0 ? (
          <p class="muted small pv-cmt-empty">Chưa có bình luận cho ảnh này.</p>
        ) : (
          comments.map((c) => (
            <div class="pv-cmt" key={c.id}>
              <div class="pv-cmt-head">
                <b>{c.username}</b>
                <span class="muted small">{fmtRelative(c.created_at)}</span>
                <button class="pv-cmt-del" title="Xoá" onClick={() => del(c)}><Icon name="trash" size={14} /></button>
              </div>
              <div class="pv-cmt-text">{c.text}</div>
            </div>
          ))
        )}
      </div>

      <div class="pv-cmt-add">
        <textarea
          ref={taRef}
          value={text}
          placeholder="Viết bình luận cho ảnh…"
          rows={1}
          onInput={(e: any) => setText(e.target.value)}
          onKeyDown={(e: any) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) add(); }}
        />
        <button class="btn primary" disabled={busy || !text.trim()} onClick={add}>Gửi</button>
      </div>
    </div>
  );
}
