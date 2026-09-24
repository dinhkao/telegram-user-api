// XEM TRƯỚC SỐNG giấy dán thùng khi đang gõ (pages/OrderBoxLabel.tsx). Dùng CHÍNH ảnh
// PNG server render cho máy in (/api/order/:id/gdt/png — server_app/gdt_routes.py) nên
// thấy đúng tờ sẽ in, không có bản vẽ thứ hai. Gõ xong 400ms mới gọi, request cũ bị
// huỷ, ảnh cũ giữ nguyên tới khi ảnh mới về (không nháy). Ảnh gốc chữ xoay dọc →
// xoay ngang 90° trên canvas để đọc được mà không phải nghiêng máy.
import { useEffect, useRef, useState } from "preact/hooks";
import { gdtPngUrl, type GdtBody } from "../api";

const DELAY_MS = 400;

async function rotatedUrl(blob: Blob): Promise<string> {
  const bmp = await createImageBitmap(blob);
  const c = document.createElement("canvas");
  c.width = bmp.height;
  c.height = bmp.width;
  const g = c.getContext("2d")!;
  g.translate(0, c.height);   // xoay NGƯỢC chiều kim đồng hồ: chữ dọc trên→dưới thành trái→phải
  g.rotate(-Math.PI / 2);
  g.drawImage(bmp, 0, 0);
  bmp.close?.();
  const out: Blob = await new Promise((ok, bad) => c.toBlob((b) => (b ? ok(b) : bad(new Error("canvas"))), "image/png"));
  return URL.createObjectURL(out);
}

export function GdtLivePreview({ threadId, body }: { threadId: string; body: GdtBody }) {
  const [src, setSrc] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const urlRef = useRef<string | null>(null);
  const ready = !!(body.ten.trim() && body.so_thung.trim());

  useEffect(() => {
    if (!ready) return;
    const ac = new AbortController();
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await fetch(gdtPngUrl(threadId, body), { signal: ac.signal, cache: "no-store" });
        if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
        const url = await rotatedUrl(await r.blob());
        if (ac.signal.aborted) { URL.revokeObjectURL(url); return; }
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = url;
        setSrc(url);
        setErr("");
      } catch (e: any) {
        if (!ac.signal.aborted) setErr(e?.message || "Lỗi tải ảnh xem trước");
      } finally {
        if (!ac.signal.aborted) setBusy(false);
      }
    }, DELAY_MS);
    return () => { clearTimeout(t); ac.abort(); };
  }, [threadId, body.ten, body.sdt, body.so_thung, body.note, ready]);

  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }, []);

  return (
    <section class="card gdt-live">
      <div class="row space">
        <b>Tờ sẽ in</b>
        <span class="muted small">{busy ? "Đang cập nhật…" : ready ? "Cập nhật theo nội dung đang gõ" : ""}</span>
      </div>
      {!ready ? (
        <p class="muted small">Nhập người nhận và số thùng để xem trước.</p>
      ) : src ? (
        <img class={`gdt-live-img${busy ? " stale" : ""}`} src={src} alt="Xem trước giấy dán thùng" />
      ) : (
        <div class="gdt-live-empty muted small">{err || "Đang tạo ảnh xem trước…"}</div>
      )}
      {err && src && <p class="small t-danger">{err}</p>}
    </section>
  );
}
