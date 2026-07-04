// Khối ẢNH của đơn — chụp/chọn ảnh, nén phía client (imageProcess), upload
// multipart, lưới thumbnail tải lười + xem phóng to (lightbox), xoá ảnh.
// Data: GET/POST/DELETE /api/order/{thread_id}/images. Realtime: order_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { deleteOrderImage, listOrderImages, orderImageUrl, postForm, type OrderImage } from "../api";
import { onRealtime } from "../realtime";
import { processImage } from "./imageProcess";
import { PhotoViewer } from "./PhotoViewer";
import { CameraBox } from "./CameraBox";

type Pending = { key: number; url: string };
let _pk = 0;

export function Images({ threadId }: { threadId: string }) {
  const [images, setImages] = useState<OrderImage[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const [err, setErr] = useState("");
  const [dbg, setDbg] = useState<string[]>([]);
  const [lightbox, setLightbox] = useState<OrderImage | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const camInput = useRef<HTMLInputElement>(null);

  // Chẩn đoán trên máy: hiện từng bước để biết ảnh gallery hỏng ở đâu
  const logDbg = (m: string) => setDbg((p) => [...p.slice(-11), m]);

  const load = async () => {
    try {
      setImages(await listOrderImages(threadId));
    } catch {
      /* mất mạng, không có cache → để trống */
    }
  };
  useEffect(() => {
    load();
  }, [threadId]);

  // Realtime: ảnh thêm/xoá từ máy khác → tải lại lưới (debounce nhẹ)
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if ((e.type === "order_changed" && e.thread_id === String(threadId)) || e.type === "resync") {
        clearTimeout(t);
        t = setTimeout(load, 300);
      }
    });
    return () => {
      clearTimeout(t);
      off();
    };
  }, [threadId]);

  const uploadOne = async (file: File): Promise<boolean> => {
    const key = ++_pk;
    let previewUrl = "";
    const nm = file.name || "?";
    try {
      const p = await processImage(file);
      previewUrl = URL.createObjectURL(p.thumb);
      setPending((prev) => [{ key, url: previewUrl }, ...prev]);
      const fd = new FormData();
      fd.append("photo", p.full, `photo${p.ext}`);
      fd.append("thumb", p.thumb, `thumb${p.ext}`);
      fd.append("width", String(p.width));
      fd.append("height", String(p.height));
      await postForm(`/api/order/${threadId}/images`, fd);
      return true;
    } catch (ex: any) {
      const m = ex?.message || String(ex);
      setErr(`Lỗi tải ${nm}: ${m}`);
      logDbg(`❌ ${nm} (${(file.size / 1024) | 0}KB, ${file.type || "no-type"}): ${m}`);
      return false;
    } finally {
      setPending((prev) => prev.filter((x) => x.key !== key));
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    }
  };

  const onPick = async (e: any) => {
    const files: FileList = e.target.files;
    setErr("");
    setDbg([]);
    if (!files || !files.length) return;
    // Ảnh từ gallery/content-provider có thể có MIME rỗng hoặc lạ → đừng lọc gắt,
    // nhận cả file không có type hoặc có đuôi ảnh (HEIC iOS…). processImage tự báo lỗi nếu không đọc được.
    const isImg = (f: File) =>
      f.type.startsWith("image/") || f.type === "" || /\.(jpe?g|png|webp|heic|heif|gif|bmp|avif|tiff?)$/i.test(f.name);
    const imgs = Array.from(files).filter(isImg);
    e.target.value = ""; // cho phép chọn lại cùng file
    if (!imgs.length) {
      setErr("Không nhận được ảnh hợp lệ từ lựa chọn.");
      return;
    }
    const oks = await Promise.all(imgs.map(uploadOne)); // upload song song cho nhanh
    await load(); // đồng bộ danh sách chuẩn từ server
    if (oks.every(Boolean)) setDbg([]); // thành công hết → ẩn khối chẩn đoán
  };

  const remove = async (img: OrderImage) => {
    if (!confirm("Xoá ảnh này?")) return;
    setImages((prev) => prev.filter((x) => x.id !== img.id)); // lạc quan
    if (lightbox?.id === img.id) setLightbox(null);
    try {
      await deleteOrderImage(threadId, img.id);
    } catch (ex: any) {
      setErr(ex?.message || "Xoá thất bại");
      load(); // khôi phục nếu lỗi
    }
  };

  const count = images.length + pending.length;

  return (
    <div class="card">
      <div class="row space">
        <b>Ảnh {count > 0 && <span class="muted small">({count})</span>}</b>
        <div class="img-actions">
          <button class="btn" onClick={() => camInput.current?.click()}>📸 Chụp</button>
          <button class="btn" onClick={() => fileInput.current?.click()}>📁 Chọn</button>
        </div>
      </div>
      <input ref={camInput} type="file" accept="image/*" capture="environment" hidden onChange={onPick} />
      {/* multiple: chọn nhiều ảnh 1 lượt. APK dùng gallery THUẦN (không trộn camera)
          cho input này nên chọn-nhiều chạy ổn; trình duyệt xử lý natively. */}
      <input ref={fileInput} type="file" accept="image/*" multiple hidden onChange={onPick} />

      {/* Camera trực tiếp trong khung (nhanh, chụp liên tiếp) — tự ẩn nếu thiếu HTTPS */}
      <CameraBox threadId={threadId} onUploaded={load} />

      {err && <p class="error small">{err}</p>}

      {dbg.length > 0 && (
        <pre class="img-dbg" onClick={() => setDbg([])}>{dbg.join("\n")}</pre>
      )}

      {count === 0 ? (
        <p class="muted small">Chưa có ảnh. Bấm 📸 Chụp hoặc 📁 Chọn để thêm.</p>
      ) : (
        <div class="img-grid">
          {pending.map((p) => (
            <div class="img-tile uploading" key={`p${p.key}`}>
              <img src={p.url} alt="" />
              <span class="img-spin" />
            </div>
          ))}
          {images.map((img) => (
            <div class="img-tile" id={`image-${img.id}`} key={img.id}>
              <img
                src={orderImageUrl(threadId, img.id, "thumb")}
                loading="lazy"
                alt=""
                onClick={() => setLightbox(img)}
              />
              <button class="img-del" title="Xoá" onClick={() => remove(img)}>×</button>
            </div>
          ))}
        </div>
      )}

      {lightbox && (
        <PhotoViewer
          images={images}
          start={Math.max(0, images.findIndex((x) => x.id === lightbox.id))}
          threadId={threadId}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
