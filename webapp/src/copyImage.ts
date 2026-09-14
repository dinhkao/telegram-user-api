// Copy 1 ẢNH vào clipboard — LÕI DUY NHẤT, dùng cho PhotoViewer lẫn các nút Copy hoá
// đơn ở OrderDetail. APK WebView không copy ảnh được bằng Clipboard API → ưu tiên cầu
// native AndroidApp.copyImage(dataUrl); trình duyệt: đổi sang PNG (clipboard chỉ chắc
// ăn với PNG) rồi ClipboardItem.
//
// ⚠ PHẢI GỌI NGAY trong handler click, KHÔNG await gì trước đó. Trình duyệt chỉ cho ghi
// clipboard khi còn "user activation" của cú bấm; bản cũ await lấy danh sách ảnh + có khi
// render PNG (vài giây) XONG mới write → activation hết hạn → NotAllowedError. Cách giữ:
// dựng ClipboardItem với GIÁ TRỊ LÀ PROMISE rồi write NGAY, phần tải ảnh chạy bên trong.
// Vì vậy API là `copyImageLazy(load)` chứ không nhận sẵn Blob.
//
// Thất bại → THROW CopyImageError kèm LÝ DO THẬT; caller hiện thẳng message đó, đừng
// quy hết về "trình duyệt chặn" (che mất ca hết hạn token, ảnh lỗi, HTTP không bảo mật).

export class CopyImageError extends Error {}

function toDataUrl(blob: Blob): Promise<string> {
  return new Promise((ok, no) => {
    const fr = new FileReader();
    fr.onload = () => ok(String(fr.result));
    fr.onerror = () => no(new CopyImageError("Đọc ảnh lỗi"));
    fr.readAsDataURL(blob);
  });
}

async function toPng(blob: Blob): Promise<Blob> {
  if (blob.type === "image/png") return blob;
  const bmp = await createImageBitmap(blob);
  const c = document.createElement("canvas");
  c.width = bmp.width;
  c.height = bmp.height;
  c.getContext("2d")!.drawImage(bmp, 0, 0);
  (bmp as any).close?.();
  return new Promise<Blob>((ok, no) =>
    c.toBlob((b) => (b ? ok(b) : no(new CopyImageError("Đổi ảnh sang PNG lỗi"))), "image/png"));
}

/** Copy ảnh do `load()` tải về. GỌI ĐỒNG BỘ TRONG HANDLER CLICK — xem ghi chú đầu file. */
export function copyImageLazy(load: () => Promise<Blob>): Promise<void> {
  const bridge: any = (window as any).AndroidApp;
  if (bridge?.copyImage) {
    // Cầu native không cần user activation → cứ await thoải mái.
    return load().then(toDataUrl).then((dataUrl) => {
      if (bridge.copyImage(dataUrl) === false) throw new CopyImageError("App không copy được ảnh");
    });
  }
  // navigator.clipboard chỉ tồn tại ở secure context. Mở app bằng http://<tên máy>:8090
  // là KHÔNG bảo mật (khác localhost) → API biến mất hẳn, không phải bị "chặn".
  if (!window.isSecureContext) {
    return Promise.reject(new CopyImageError(
      "Trang đang mở qua HTTP nên trình duyệt không cho copy ảnh — mở lại bằng địa chỉ https://"));
  }
  const CI: any = (window as any).ClipboardItem;
  if (!navigator.clipboard?.write || !CI) {
    return Promise.reject(new CopyImageError("Trình duyệt này không copy được ảnh — dùng nút Tải về"));
  }

  const png = load().then(toPng);
  let item: any;
  try {
    item = new CI({ "image/png": png });        // Safari/Chrome hiện đại nhận Promise
  } catch {
    // Trình duyệt cũ chỉ nhận Blob → đành await trước (có thể mất activation, nhưng
    // còn hơn không thử).
    return png.then((b) => navigator.clipboard.write([new CI({ "image/png": b })]))
      .catch((e: any) => { throw new CopyImageError(e?.message || "Copy ảnh lỗi"); });
  }
  png.catch(() => {});                          // tránh unhandled rejection nếu write hỏng trước
  return navigator.clipboard.write([item]).catch((e: any) => {
    if (e instanceof CopyImageError) throw e;
    const m = String(e?.name === "NotAllowedError"
      ? "Trình duyệt không cho copy (cửa sổ phải đang được chọn) — thử bấm lại"
      : e?.message || "Copy ảnh lỗi");
    throw new CopyImageError(m);
  });
}

/** Tiện ích: copy ảnh từ 1 URL. Cũng phải gọi đồng bộ trong handler click. */
export function copyImageFromUrl(url: string): Promise<void> {
  return copyImageLazy(async () => {
    const res = await fetch(url);
    if (!res.ok) throw new CopyImageError(`Tải ảnh lỗi (HTTP ${res.status})`);
    return res.blob();
  });
}
