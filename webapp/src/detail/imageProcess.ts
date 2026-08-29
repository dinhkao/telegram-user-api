// Nén ảnh phía client TRƯỚC khi upload — điểm mấu chốt về tốc độ. Ảnh gốc điện
// thoại 3–8MB → giảm còn ~100–250KB: co về cạnh dài tối đa 1600px, mã hoá WebP
// (rớt về JPEG với mức nén RIÊNG nếu thiết bị không encode được WebP), tạo thumbnail ~400px
// (~10–20KB) để lưới gallery tải tức thì. Tôn trọng xoay EXIF. Dùng: detail/Images.

const FULL_MAX = 1600;
const THUMB_MAX = 400;

// Chất lượng nén ĐỂ RIÊNG THEO ĐỊNH DẠNG. WebP nén tốt hơn JPEG rất nhiều ở
// cùng mức q, nên dùng chung một con số là máy rớt về JPEG (iPhone/Safari không
// encode được WebP qua canvas) tải lên file nặng gấp 2–3,7 lần cùng kích thước
// ảnh — đo 29/08/2026 trên kho ảnh thật: 384KB/ảnh JPEG vs 151KB/ảnh WebP ở
// scope `box`, 487KB vs 130KB ở `report_bg`. Hạ q của JPEG cho cân lại.
const QUALITY: Record<string, { full: number; thumb: number }> = {
  "image/webp": { full: 0.82, thumb: 0.7 },
  "image/jpeg": { full: 0.7, thumb: 0.62 },
};
const JPEG_Q = QUALITY["image/jpeg"];

export type Processed = {
  full: Blob;
  thumb: Blob;
  width: number; // kích thước ảnh 'full' sau khi co
  height: number;
  ext: string; // '.webp' | '.jpg'
  mime: string;
};

let _webpOk: boolean | null = null;
/** Thiết bị có mã hoá được WebP qua canvas không (cache 1 lần). */
function webpSupported(): boolean {
  if (_webpOk !== null) return _webpOk;
  try {
    const c = document.createElement("canvas");
    c.width = c.height = 1;
    _webpOk = c.toDataURL("image/webp").startsWith("data:image/webp");
  } catch {
    _webpOk = false;
  }
  return _webpOk;
}

function scaled(w: number, h: number, max: number): [number, number] {
  if (w <= max && h <= max) return [w, h];
  const r = Math.min(max / w, max / h);
  return [Math.round(w * r), Math.round(h * r)];
}

async function encode(src: CanvasImageSource, w: number, h: number, mime: string, q: number, jpegQ: number): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, 0, 0, w, h);
  const blob: Blob | null = await new Promise((res) => canvas.toBlob(res, mime, q));
  if (blob) return blob;
  // rớt về JPEG nếu mime không được hỗ trợ — dùng q của JPEG, không phải q của
  // định dạng vừa hỏng (q của WebP đem sang JPEG là ra file nặng gấp mấy lần).
  return await new Promise((res, rej) =>
    canvas.toBlob((b) => (b ? res(b) : rej(new Error("encode ảnh thất bại"))), "image/jpeg", jpegQ)
  );
}

type Source = { src: CanvasImageSource; width: number; height: number; done: () => void };

/** Giải mã File ảnh thành nguồn vẽ được lên canvas.
 *  Ưu tiên createImageBitmap (nhanh, tôn trọng EXIF); nếu lỗi (một số ảnh gallery,
 *  HEIC iOS…) → rớt về <img> element (Safari tự giải mã HEIC, tự xoay EXIF). */
async function loadSource(file: File): Promise<Source> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    return { src: bmp, width: bmp.width, height: bmp.height, done: () => bmp.close?.() };
  } catch {
    /* thử tiếp */
  }
  try {
    const bmp = await createImageBitmap(file); // trình duyệt cũ không nhận option
    return { src: bmp, width: bmp.width, height: bmp.height, done: () => bmp.close?.() };
  } catch {
    /* rớt về <img> */
  }
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((res, rej) => {
      const im = new Image();
      im.onload = () => res(im);
      im.onerror = () => rej(new Error("không đọc được ảnh (định dạng không hỗ trợ?)"));
      im.src = url;
    });
    return {
      src: img,
      width: img.naturalWidth || img.width,
      height: img.naturalHeight || img.height,
      done: () => URL.revokeObjectURL(url),
    };
  } catch (e) {
    URL.revokeObjectURL(url);
    throw e;
  }
}

/** Nén sẵn một nguồn vẽ được (canvas/bitmap/img) → { full, thumb }. Dùng cho
 *  camera trực tiếp (bắt frame <video> ra canvas) khỏi phải đi vòng qua File. */
export async function processSource(src: CanvasImageSource, width: number, height: number): Promise<Processed> {
  if (!width || !height) throw new Error("ảnh không hợp lệ (kích thước 0)");
  const useWebp = webpSupported();
  const mime = useWebp ? "image/webp" : "image/jpeg";
  const ext = useWebp ? ".webp" : ".jpg";
  const q = QUALITY[mime];

  const [fw, fh] = scaled(width, height, FULL_MAX);
  const [tw, th] = scaled(width, height, THUMB_MAX);
  const [full, thumb] = await Promise.all([
    encode(src, fw, fh, mime, q.full, JPEG_Q.full),
    encode(src, tw, th, mime, q.thumb, JPEG_Q.thumb),
  ]);
  return { full, thumb, width: fw, height: fh, ext, mime };
}

/** Đọc File ảnh → { full, thumb, dims }. Ném lỗi nếu không giải mã được. */
export async function processImage(file: File): Promise<Processed> {
  const s = await loadSource(file);
  try {
    return await processSource(s.src, s.width, s.height);
  } finally {
    s.done();
  }
}
