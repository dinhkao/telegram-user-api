// Khối ẢNH dùng chung — chụp/chọn ảnh, nén phía client (imageProcess), upload
// multipart, lưới thumbnail tải lười + xem phóng to (lightbox), xoá ảnh.
// Data: GET/POST/DELETE {base}/images (base vd /api/order/123 hoặc /api/media/box/5).
import { useEffect, useRef, useState } from "preact/hooks";
import { deleteMediaImage, listMediaImages, mediaImageUrl, postForm, type OrderImage } from "../api";
import { onRealtime, eventMatchesBase } from "../realtime";
import { processImage } from "./imageProcess";
import { PhotoViewer } from "./PhotoViewer";
import { CameraBox, cameraSupported } from "./CameraBox";
import { confirmDialog } from "../ui/feedback";
import { KIND_ORDER, KIND_LABEL, KIND_ICON, kindOf, isOrderBase } from "./imageKinds";

type Pending = { key: number; url: string };
let _pk = 0;

export function Images({ base, anchorId, openSignal }: { base: string; anchorId?: string; openSignal?: number }) {
  const [images, setImages] = useState<OrderImage[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const [err, setErr] = useState("");
  const [dbg, setDbg] = useState<string[]>([]);
  const [lightbox, setLightbox] = useState<OrderImage | null>(null);
  const [camOpen, setCamOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Phân loại chỉ áp dụng cho ảnh ĐƠN HÀNG (không cho thùng/phiếu SX).
  const isOrder = isOrderBase(base);
  const [uploadKind, setUploadKind] = useState<string>("soan_hang");  // loại gán cho ảnh sắp tải
  const [filter, setFilter] = useState<string>("all");                // lọc lưới theo loại

  // Chẩn đoán trên máy: hiện từng bước để biết ảnh gallery hỏng ở đâu
  const logDbg = (m: string) => setDbg((p) => [...p.slice(-11), m]);

  const load = async () => {
    try {
      setImages(await listMediaImages(base));
    } catch {
      /* mất mạng, không có cache → để trống */
    }
  };
  useEffect(() => {
    load();
  }, [base]);

  // Nút "Chụp ảnh" ở thanh điều hướng nhanh (OrderDetail) tăng openSignal → mở camera
  // trong khung (nếu có HTTPS) hoặc bật hộp chọn ảnh của máy (mở được camera).
  useEffect(() => {
    if (!openSignal) return;
    if (cameraSupported()) setCamOpen(true);
    else fileInput.current?.click();
  }, [openSignal]);

  // Realtime: ảnh thêm/xoá trên CÙNG thực thể (từ máy khác / Telegram) → tải lại lưới
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (eventMatchesBase(base, e)) { clearTimeout(t); t = setTimeout(load, 300); }
    });
    return () => { clearTimeout(t); off(); };
  }, [base]);

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
      if (isOrder) fd.append("kind", uploadKind);
      await postForm(`${base}/images`, fd);
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
    if (!(await confirmDialog("Xoá ảnh này?", { danger: true }))) return;
    setImages((prev) => prev.filter((x) => x.id !== img.id)); // lạc quan
    if (lightbox?.id === img.id) setLightbox(null);
    try {
      await deleteMediaImage(base, img.id);
    } catch (ex: any) {
      setErr(ex?.message || "Xoá thất bại");
      load(); // khôi phục nếu lỗi
    }
  };

  // Lưới hiển thị (đã lọc theo loại nếu đang chọn); đếm theo loại cho chip lọc.
  const shown = isOrder && filter !== "all" ? images.filter((x) => kindOf(x) === filter) : images;
  const kindCounts: Record<string, number> = {};
  if (isOrder) for (const x of images) kindCounts[kindOf(x)] = (kindCounts[kindOf(x)] || 0) + 1;
  const count = images.length + pending.length;

  return (
    <div class="card" id={anchorId}>
      <div class="row space">
        <b>Ảnh {count > 0 && <span class="muted small">({count})</span>}</b>
      </div>
      {/* multiple: chọn nhiều ảnh 1 lượt. APK dùng gallery THUẦN (không trộn camera)
          cho input này nên chọn-nhiều chạy ổn; trình duyệt xử lý natively. */}
      <input ref={fileInput} type="file" accept="image/*" multiple hidden onChange={onPick} />

      {/* Camera trực tiếp trong khung (nhanh, chụp liên tiếp). Nút mở camera chỉ
          hiện khi có HTTPS; nếu không → chỉ còn nút Chọn ảnh từ máy. */}
      {/* Loại ảnh sắp tải (chỉ đơn hàng) — ảnh mới sẽ gắn loại này. */}
      {isOrder && !camOpen && (
        <div class="img-kindpick">
          <span class="muted small">Loại:</span>
          {KIND_ORDER.map((k) => (
            <button key={k} class={"kchip" + (uploadKind === k ? " on" : "")} onClick={() => setUploadKind(k)}>
              {KIND_ICON[k]} {KIND_LABEL[k]}
            </button>
          ))}
        </div>
      )}

      {camOpen ? (
        <CameraBox base={base} kind={isOrder ? uploadKind : undefined} onUploaded={load} onClose={() => setCamOpen(false)} />
      ) : (
        <div class="img-actions">
          {cameraSupported() && (
            <button class="btn cam-primary" onClick={() => setCamOpen(true)}>🎥 Mở camera</button>
          )}
          <button class="btn" onClick={() => fileInput.current?.click()}>📁 Chọn ảnh</button>
        </div>
      )}

      {err && <p class="error small">{err}</p>}

      {dbg.length > 0 && (
        <pre class="img-dbg" onClick={() => setDbg([])}>{dbg.join("\n")}</pre>
      )}

      {/* Lọc theo loại (chỉ đơn hàng, khi đã có ảnh). */}
      {isOrder && images.length > 0 && (
        <div class="img-filter">
          <button class={"kchip" + (filter === "all" ? " on" : "")} onClick={() => setFilter("all")}>Tất cả ({images.length})</button>
          {KIND_ORDER.filter((k) => kindCounts[k]).map((k) => (
            <button key={k} class={"kchip" + (filter === k ? " on" : "")} onClick={() => setFilter(k)}>
              {KIND_ICON[k]} {KIND_LABEL[k]} ({kindCounts[k]})
            </button>
          ))}
        </div>
      )}

      {count === 0 ? (
        <p class="muted small">Chưa có ảnh. Bấm 📸 Chụp hoặc 📁 Chọn để thêm.</p>
      ) : shown.length === 0 && pending.length === 0 ? (
        <p class="muted small">Không có ảnh loại này.</p>
      ) : (
        <div class="img-grid">
          {pending.map((p) => (
            <div class="img-tile uploading" key={`p${p.key}`}>
              <img src={p.url} alt="" />
              <span class="img-spin" />
            </div>
          ))}
          {shown.map((img) => (
            <div class="img-tile" id={`image-${img.id}`} key={img.id}>
              <img
                src={mediaImageUrl(base, img.id, "thumb")}
                loading="lazy"
                alt=""
                onClick={() => setLightbox(img)}
              />
              <button class="img-del" title="Xoá" onClick={() => remove(img)}>×</button>
              {isOrder && (
                <span class="img-kind" title={KIND_LABEL[kindOf(img)]}>{KIND_ICON[kindOf(img)]} {KIND_LABEL[kindOf(img)]}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {lightbox && (
        <PhotoViewer
          images={images}
          start={Math.max(0, images.findIndex((x) => x.id === lightbox.id))}
          base={base}
          editable={isOrder}
          onKindChange={(id, kind) => setImages((prev) => prev.map((x) => (x.id === id ? { ...x, kind } : x)))}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
