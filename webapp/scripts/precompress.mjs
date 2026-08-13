// Nén SẴN dist sau `vite build` → aiohttp `web.FileResponse` tự phục vụ file
// `.br`/`.gz` nằm cạnh khi client gửi Accept-Encoding (server không có middleware
// nén). Đáng làm vì APK đặt cacheMode=LOAD_NO_CACHE: mỗi lần mở nguội là tải lại
// TOÀN BỘ bundle (~1,3MB thô) qua Tailscale.
// Chạy tự động trong `npm run build` (package.json). Không nén file nhỏ (<1KB) và
// bỏ kết quả nếu nén xong không nhỏ hơn bản gốc.
import { readdirSync, statSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { join, dirname, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync, brotliCompressSync, constants } from "node:zlib";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const EXT = new Set([".js", ".css", ".html", ".svg", ".json", ".map"]);
const MIN_SIZE = 1024;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

let files;
try {
  files = walk(DIST);
} catch {
  console.error("precompress: chưa có dist — bỏ qua");
  process.exit(0);
}

// Dọn bản nén cũ trước (tên file có hash nên rác không tự biến mất khi đổi build).
for (const f of files) {
  if (f.endsWith(".gz") || f.endsWith(".br")) rmSync(f, { force: true });
}

let saved = 0;
let n = 0;
for (const f of files) {
  if (f.endsWith(".gz") || f.endsWith(".br")) continue;
  if (!EXT.has(extname(f))) continue;
  const raw = readFileSync(f);
  if (raw.length < MIN_SIZE) continue;
  const gz = gzipSync(raw, { level: 9 });
  const br = brotliCompressSync(raw, {
    params: {
      [constants.BROTLI_PARAM_QUALITY]: 11,
      [constants.BROTLI_PARAM_SIZE_HINT]: raw.length,
    },
  });
  if (gz.length < raw.length) writeFileSync(f + ".gz", gz);
  if (br.length < raw.length) writeFileSync(f + ".br", br);
  saved += raw.length - Math.min(gz.length, br.length);
  n++;
}
console.log(`precompress: ${n} file, tiết kiệm ~${Math.round(saved / 1024)}KB mỗi lần tải nguội`);
