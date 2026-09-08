// Renderer MARKDOWN nhỏ, thuần, KHÔNG thư viện — dùng cho nhận định AI của bản
// dự báo hàng hoá (pages/ForecastDetail). Escape HTML TRƯỚC rồi mới chuyển cú
// pháp, nên chuỗi từ server không chèn được thẻ/script. Hỗ trợ: #/##/###,
// **đậm**, *nghiêng*, danh sách "- " và "1. ", bảng "| a | b |" (dòng |---| tách
// header, "---:" = căn phải), đoạn văn. Không link/ảnh (không cần, và mở đường XSS).
// Xuất HTML để render qua dangerouslySetInnerHTML với class .md-body.

/** Escape 5 ký tự HTML — chạy TRƯỚC mọi bước chuyển cú pháp. */
export function escapeHtml(s: string): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Đậm/nghiêng trong 1 đoạn chữ ĐÃ escape. Đậm trước → dấu * còn lại là nghiêng. */
function inline(escaped: string): string {
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*\n]+)\*/g, "<i>$1</i>");
}

/** Dòng "| a | b |" → các ô đã trim (bỏ ô rỗng đầu/cuối do dấu | bao ngoài). */
function tableCells(line: string): string[] {
  const t = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return t.split("|").map((c) => c.trim());
}

const isTableLine = (l: string) => /^\s*\|.*\|\s*$/.test(l);
const isTableSep = (l: string) => /^\s*\|[\s:|-]*-[\s:|-]*\|\s*$/.test(l);

export function renderMarkdown(md: string): string {
  const lines = String(md ?? "").replace(/\r\n?/g, "\n").split("\n");
  const out: string[] = [];
  let para: string[] = [];

  const flushPara = () => {
    if (!para.length) return;
    out.push(`<p>${inline(escapeHtml(para.join(" ")))}</p>`);
    para = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trimEnd();

    if (!line.trim()) { flushPara(); continue; }

    // Tiêu đề: # → h3 (h1/h2 đã là tiêu đề trang/khối)
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      flushPara();
      const lv = h[1].length + 2;   // # → h3, ## → h4, ### → h5
      out.push(`<h${lv}>${inline(escapeHtml(h[2].trim()))}</h${lv}>`);
      continue;
    }

    // Bảng: dòng |…| liên tiếp; dòng |---| ngay sau dòng đầu = tách header
    if (isTableLine(line)) {
      flushPara();
      const block: string[] = [];
      let k = i;
      while (k < lines.length && isTableLine(lines[k])) { block.push(lines[k]); k++; }
      i = k - 1;   // dừng ĐÚNG dòng cuối của bảng, vòng ngoài đi tiếp dòng sau

      let head: string[] | null = null;
      let body = block;
      if (block.length >= 2 && isTableSep(block[1])) {
        head = tableCells(block[0]);
        body = block.slice(2);
      }
      // Căn phải theo dấu ":" cuối ô của dòng tách ("---:") — cột số cho dễ đọc.
      const align = head ? tableCells(block[1]).map((c) => c.endsWith(":") && !c.startsWith(":")) : [];
      const cell = (c: string, tag: string, i: number) =>
        `<${tag}${align[i] ? ' class="num"' : ""}>${inline(escapeHtml(c))}</${tag}>`;
      let html = "<table>";
      if (head) html += `<thead><tr>${head.map((c, i) => cell(c, "th", i)).join("")}</tr></thead>`;
      html += "<tbody>";
      for (const r of body) {
        if (isTableSep(r)) continue;
        html += `<tr>${tableCells(r).map((c, i) => cell(c, "td", i)).join("")}</tr>`;
      }
      html += "</tbody></table>";
      out.push(html);
      continue;
    }

    // Danh sách: "- " (ul) hoặc "1. " (ol) — gom các dòng liên tiếp cùng loại
    const isUl = /^\s*[-*]\s+/.test(line);
    const isOl = /^\s*\d+[.)]\s+/.test(line);
    if (isUl || isOl) {
      flushPara();
      const tag = isUl ? "ul" : "ol";
      const items: string[] = [];
      let k = i;
      while (k < lines.length) {
        const l = lines[k];
        const u = /^\s*[-*]\s+(.*)$/.exec(l);
        const o = /^\s*\d+[.)]\s+(.*)$/.exec(l);
        if (isUl && u) items.push(u[1]);
        else if (isOl && o) items.push(o[1]);
        else break;
        k++;
      }
      i = k - 1;
      out.push(`<${tag}>${items.map((t) => `<li>${inline(escapeHtml(t.trim()))}</li>`).join("")}</${tag}>`);
      continue;
    }

    para.push(line.trim());
  }
  flushPara();
  return out.join("\n");
}
