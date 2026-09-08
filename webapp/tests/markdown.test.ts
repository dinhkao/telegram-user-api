// Renderer markdown nhỏ (src/detail/markdown.ts) — dùng cho nhận định AI của bản
// dự báo. Nội dung tới từ server nên phải ESCAPE HTML trước; test khoá cả 3 mặt:
// an toàn (không lọt thẻ), bảng, danh sách.
import assert from "node:assert/strict";
import test from "node:test";
import { escapeHtml, renderMarkdown } from "../src/detail/markdown.ts";

test("escape HTML trước khi chuyển cú pháp — không lọt thẻ/script", () => {
  const html = renderMarkdown('<script>alert(1)</script> & "x" <b>đậm giả</b>');
  assert.ok(!html.includes("<script"));
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes("&amp;"));
  assert.ok(html.includes("&quot;"));
  assert.equal(escapeHtml("<a href='x'>"), "&lt;a href=&#39;x&#39;&gt;");
});

test("escape rồi mới in đậm/nghiêng — chữ trong thẻ vẫn là chữ", () => {
  assert.equal(renderMarkdown("**Cần <b>gấp</b>**"), "<p><b>Cần &lt;b&gt;gấp&lt;/b&gt;</b></p>");
  assert.equal(renderMarkdown("chú *nghiêng* thôi"), "<p>chú <i>nghiêng</i> thôi</p>");
});

test("tiêu đề # / ## / ###", () => {
  assert.equal(renderMarkdown("# To"), "<h3>To</h3>");
  assert.equal(renderMarkdown("## Vừa"), "<h4>Vừa</h4>");
  assert.equal(renderMarkdown("### Nhỏ"), "<h5>Nhỏ</h5>");
});

test("danh sách gạch đầu dòng và đánh số", () => {
  assert.equal(renderMarkdown("- một\n- hai"), "<ul><li>một</li><li>hai</li></ul>");
  assert.equal(renderMarkdown("1. một\n2. hai"), "<ol><li>một</li><li>hai</li></ol>");
});

test("danh sách kết thúc đúng chỗ — đoạn văn sau không bị nuốt", () => {
  const html = renderMarkdown("- một\n- hai\n\nĐoạn sau");
  assert.equal(html, "<ul><li>một</li><li>hai</li></ul>\n<p>Đoạn sau</p>");
});

test("bảng có dòng |---| tách header", () => {
  const html = renderMarkdown("| Nhóm | SL |\n|---|---|\n| Kẹo dừa | 120 |");
  assert.equal(
    html,
    "<table><thead><tr><th>Nhóm</th><th>SL</th></tr></thead>"
    + "<tbody><tr><td>Kẹo dừa</td><td>120</td></tr></tbody></table>",
  );
});

test("bảng không có dòng tách → mọi dòng là thân bảng, và dừng đúng cuối bảng", () => {
  const html = renderMarkdown("| a | b |\n| c | d |\nSau bảng");
  assert.equal(
    html,
    "<table><tbody><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></tbody></table>\n<p>Sau bảng</p>",
  );
});

test("đoạn văn: dòng liền nhau gộp 1 đoạn, dòng trống tách đoạn", () => {
  assert.equal(renderMarkdown("một\nhai\n\nba"), "<p>một hai</p>\n<p>ba</p>");
  assert.equal(renderMarkdown(""), "");
});

test("dòng tách \"---:\" → cột căn phải (class num)", () => {
  const html = renderMarkdown("| Nhóm | Dự báo |\n|---|---:|\n| Kẹo dừa | 120 |");
  assert.ok(html.includes('<th class="num">Dự báo</th>'));
  assert.ok(html.includes('<td class="num">120</td>'));
  assert.ok(html.includes("<th>Nhóm</th>"));   // cột trái không gắn class
});
