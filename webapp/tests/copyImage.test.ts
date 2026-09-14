// copyImageLazy: giữ "user activation" của cú bấm + báo đúng lý do khi không copy được.
//
// Bẫy đã dính 14/09/2026: nút Copy hoá đơn await tìm/render ảnh (1–vài giây) XONG mới
// gọi clipboard.write → hết activation → trình duyệt từ chối, mà caller lại nuốt thành
// "trình duyệt chặn" nên soi mãi không ra. Test 1 khoá đúng chuyện đó.
import assert from "node:assert/strict";
import test from "node:test";
import { CopyImageError, copyImageLazy } from "../src/copyImage.ts";

type Env = { writes: any[][]; loaded: number };

/** Dựng môi trường trình duyệt giả. `secure` = isSecureContext, `bridge` = cầu APK. */
function fakeBrowser(opts: { secure?: boolean; bridge?: (d: string) => boolean } = {}): Env {
  const env: Env = { writes: [], loaded: 0 };
  const win: any = {
    isSecureContext: opts.secure !== false,
    // KHÔNG dùng "constructor(public data)" — node --test chạy strip-only, không nhận
    ClipboardItem: class { data: any; constructor(data: any) { this.data = data; } },
  };
  if (opts.bridge) win.AndroidApp = { copyImage: opts.bridge };
  (globalThis as any).window = win;
  (globalThis as any).ClipboardItem = win.ClipboardItem;
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { clipboard: { write: async (items: any[]) => {
      env.writes.push(items);
      // clipboard.write thật CHỜ promise trong ClipboardItem và hỏng theo nó —
      // fake phải giống, không thì lỗi tải ảnh bị nuốt mất.
      for (const it of items) for (const k of Object.keys(it.data)) await it.data[k];
    } } },
  });
  (globalThis as any).FileReader = class {
    onload: any; onerror: any; result = "data:image/png;base64,AA==";
    readAsDataURL() { queueMicrotask(() => this.onload?.()); }
  };
  return env;
}

const png = () => new Blob([new Uint8Array([1, 2, 3])], { type: "image/png" });

test("gọi clipboard.write NGAY, không đợi tải ảnh xong (giữ user activation)", async () => {
  const env = fakeBrowser();
  let release!: (b: Blob) => void;
  const slow = new Promise<Blob>((ok) => { release = ok; });

  const p = copyImageLazy(() => { env.loaded++; return slow; });

  // Chưa trả ảnh mà write đã phải được gọi — đây là điểm mấu chốt.
  assert.equal(env.writes.length, 1, "phải write ngay trong cùng lượt, trước khi ảnh về");
  assert.equal(env.loaded, 1, "vẫn phải bắt đầu tải ảnh");
  release(png());
  await p;
});

test("ClipboardItem nhận PROMISE chứ không phải Blob đã await", async () => {
  const env = fakeBrowser();
  const p = copyImageLazy(async () => png());
  const item = env.writes[0][0];
  assert.ok(typeof item.data["image/png"]?.then === "function", "giá trị phải là Promise");
  await p;
});

test("trang HTTP: báo rõ phải mở https, KHÔNG tải ảnh vô ích", async () => {
  const env = fakeBrowser({ secure: false });
  await assert.rejects(
    () => copyImageLazy(async () => { env.loaded++; return png(); }),
    (e: any) => e instanceof CopyImageError && /https/i.test(e.message),
  );
  assert.equal(env.loaded, 0);
  assert.equal(env.writes.length, 0);
});

test("APK: dùng cầu native, không đụng clipboard của trình duyệt", async () => {
  const seen: string[] = [];
  const env = fakeBrowser({ bridge: (d) => { seen.push(d); return true; } });
  await copyImageLazy(async () => png());
  assert.equal(seen.length, 1);
  assert.ok(seen[0].startsWith("data:image/png"));
  assert.equal(env.writes.length, 0);
});

test("cầu native trả false → lỗi nói app không copy được", async () => {
  fakeBrowser({ bridge: () => false });
  await assert.rejects(
    () => copyImageLazy(async () => png()),
    (e: any) => e instanceof CopyImageError && /App/.test(e.message),
  );
});

test("lỗi tải ảnh giữ nguyên message, không quy về 'trình duyệt chặn'", async () => {
  fakeBrowser();
  await assert.rejects(
    () => copyImageLazy(async () => { throw new CopyImageError("Tải ảnh hoá đơn lỗi (HTTP 404)"); }),
    (e: any) => /HTTP 404/.test(e.message),
  );
});
