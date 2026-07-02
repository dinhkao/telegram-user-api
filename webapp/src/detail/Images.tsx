// Khối ẢNH của đơn — chụp/chọn ảnh, nén phía client (imageProcess), upload
// multipart, lưới thumbnail tải lười + xem phóng to (lightbox), xoá ảnh.
// Data: GET/POST/DELETE /api/order/{thread_id}/images. Realtime: order_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { deleteOrderImage, listOrderImages, orderImageUrl, postForm, type OrderImage } from "../api";
import { onRealtime } from "../realtime";
import { processImage } from "./imageProcess";
import { fmtTime } from "../format";

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

  const uploadOne = async (file: File) => {
    const key = ++_pk;
    let previewUrl = "";
    const nm = file.name || "?";
    try {
      logDbg(`⏳ xử lý ${nm}…`);
      const p = await processImage(file);
      logDbg(`✓ nén: full ${(p.full.size / 1024) | 0}KB, thumb ${(p.thumb.size / 1024) | 0}KB (${p.width}×${p.height})`);
      previewUrl = URL.createObjectURL(p.thumb);
      setPending((prev) => [{ key, url: previewUrl }, ...prev]);
      const fd = new FormData();
      fd.append("photo", p.full, `photo${p.ext}`);
      fd.append("thumb", p.thumb, `thumb${p.ext}`);
      fd.append("width", String(p.width));
      fd.append("height", String(p.height));
      logDbg(`⏫ đang tải lên…`);
      await postForm(`/api/order/${threadId}/images`, fd);
      logDbg(`✅ xong ${nm}`);
    } catch (ex: any) {
      const m = ex?.message || String(ex);
      setErr(`Lỗi tải ${nm}: ${m}`);
      logDbg(`❌ LỖI ${nm}: ${m}`);
    } finally {
      setPending((prev) => prev.filter((x) => x.key !== key));
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    }
  };

  const onPick = async (e: any) => {
    const files: FileList = e.target.files;
    setErr("");
    setDbg([]);
    if (!files || !files.length) {
      logDbg("⚠️ không nhận được file nào từ trình chọn");
      return;
    }
    const all = Array.from(files);
    all.forEach((f) => logDbg(`📄 ${f.name || "?"} · ${f.type || "no-type"} · ${(f.size / 1024) | 0}KB`));
    // Ảnh từ gallery/content-provider có thể có MIME rỗng hoặc lạ → đừng lọc gắt,
    // nhận cả file không có type hoặc có đuôi ảnh (HEIC iOS…). processImage tự báo lỗi nếu không đọc được.
    const isImg = (f: File) =>
      f.type.startsWith("image/") || f.type === "" || /\.(jpe?g|png|webp|heic|heif|gif|bmp|avif|tiff?)$/i.test(f.name);
    const imgs = all.filter(isImg);
    e.target.value = ""; // cho phép chọn lại cùng file
    if (!imgs.length) {
      setErr("Không nhận được ảnh hợp lệ từ lựa chọn.");
      logDbg("❌ tất cả bị loại bởi bộ lọc (type/đuôi)");
      return;
    }
    if (imgs.length < all.length) logDbg(`⚠️ ${all.length - imgs.length} file bị loại`);
    await Promise.all(imgs.map(uploadOne)); // upload song song cho nhanh
    await load(); // đồng bộ danh sách chuẩn từ server
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
            <div class="img-tile" key={img.id}>
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
        <div class="lightbox" onClick={() => setLightbox(null)}>
          <img src={orderImageUrl(threadId, lightbox.id, "full")} alt="" onClick={(e: any) => e.stopPropagation()} />
          <div class="lightbox-bar" onClick={(e: any) => e.stopPropagation()}>
            <span class="muted small">{lightbox.uploaded_by} · {fmtTime(lightbox.created_at)}</span>
            <div class="row">
              <a class="btn" href={orderImageUrl(threadId, lightbox.id, "full")} target="_blank" rel="noreferrer">Mở gốc</a>
              <button class="btn danger" onClick={() => remove(lightbox)}>Xoá</button>
              <button class="btn" onClick={() => setLightbox(null)}>Đóng</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
