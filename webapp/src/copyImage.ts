// Copy 1 ẢNH vào clipboard từ URL — LÕI DUY NHẤT, dùng cho PhotoViewer lẫn các
// nút Copy hoá đơn ở OrderDetail. APK WebView không copy ảnh được bằng Clipboard
// API → ưu tiên cầu native AndroidApp.copyImage(dataUrl); trình duyệt: đổi sang
// PNG (clipboard chỉ chắc ăn với PNG) rồi ClipboardItem (cần HTTPS).
// Thất bại → THROW; caller tự toast/flash theo ngữ cảnh.

async function copyImageBlob(blob: Blob): Promise<void> {
  const bridge: any = (window as any).AndroidApp;
  if (bridge?.copyImage) {
    const dataUrl: string = await new Promise((ok, no) => {
      const fr = new FileReader();
      fr.onload = () => ok(String(fr.result));
      fr.onerror = () => no(new Error("read"));
      fr.readAsDataURL(blob);
    });
    if (bridge.copyImage(dataUrl) === false) throw new Error("bridge copy");
    return;
  }
  const bmp = await createImageBitmap(blob);
  const c = document.createElement("canvas");
  c.width = bmp.width;
  c.height = bmp.height;
  c.getContext("2d")!.drawImage(bmp, 0, 0);
  (bmp as any).close?.();
  const png = await new Promise<Blob>((ok, no) => c.toBlob((b) => (b ? ok(b) : no(new Error("png"))), "image/png"));
  await navigator.clipboard.write([new (window as any).ClipboardItem({ "image/png": png })]);
}

export async function copyImageFromUrl(url: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  await copyImageBlob(await res.blob());
}
