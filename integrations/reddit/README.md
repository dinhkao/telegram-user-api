# Reddit qua Cloudflare Worker (đọc + tổng hợp)

**Vấn đề:** IP Viettel VN của máy bị Reddit/Cloudflare chặn ở tầng mạng (403 cả
`.json` ẩn danh lẫn `oauth.reddit.com`). Auth không cứu được vì chặn xảy ra
TRƯỚC khi Reddit thấy token. → Phải đi qua một egress non-VN.

**Cách giải:** một Cloudflare Worker (`worker.js`) chạy ở edge (IP non-VN) làm
proxy OAuth read-only. Máy → Worker → Reddit. Miễn phí (100k req/ngày).

```
Mac (server.py, IP VN bị chặn)
  → https://<name>.workers.dev/r/<sub>/top   (x-proxy-secret)
    → Worker lấy app-only token, gọi oauth.reddit.com
      → trả JSON Reddit  → Claude tổng hợp digest tiếng Việt
```

## Setup (một lần, ~5 phút)

### 1. Tạo Reddit "script" app (miễn phí)
1. Vào https://www.reddit.com/prefs/apps (mở bằng điện thoại 4G nếu web bị chặn).
2. **create another app…** → chọn loại **script**.
3. name: `letrang-reddit`; redirect uri: `http://localhost` (không dùng nhưng bắt buộc điền).
4. Tạo xong, copy 2 giá trị:
   - **client_id** = chuỗi ngay DƯỚI tên app (dòng "personal use script").
   - **secret** = ô `secret`.

### 2. Deploy Worker
**Cách A — wrangler (CLI):**
```bash
npm i -g wrangler
cd integrations/reddit
wrangler login
wrangler deploy worker.js --name letrang-reddit --compatibility-date 2024-01-01
wrangler secret put REDDIT_CLIENT_ID       # dán client_id
wrangler secret put REDDIT_CLIENT_SECRET   # dán secret
wrangler secret put PROXY_SECRET           # tự đặt chuỗi ngẫu nhiên dài
```
**Cách B — Dashboard:** Cloudflare → Workers & Pages → Create → Worker → dán nội
dung `worker.js` → Deploy → Settings → Variables → thêm 3 secret ở trên.

URL Worker sẽ là `https://letrang-reddit.<tài-khoản>.workers.dev`.

### 3. Khai báo cho máy
Thêm vào `.env` (hoặc export) trên máy chạy `server.py`:
```
REDDIT_PROXY_URL=https://letrang-reddit.<tài-khoản>.workers.dev
REDDIT_PROXY_SECRET=<đúng PROXY_SECRET đã đặt ở bước 2>
```

### 4. Smoke-test (BẮT BUỘC — xác nhận Worker qua được cổng chặn Reddit)
```bash
.venv/bin/python tools/reddit_digest.py --smoke
```
- `reddit fetch: OK` → xong, dùng được.
- `FAIL … bị chặn` → IP edge của Worker cũng bị Reddit đánh dấu (hiếm) → chuyển
  sang phương án VPS (xem thảo luận). Rất ít khi xảy ra.

## Dùng
```bash
# Top tuần của vài subreddit
.venv/bin/python tools/reddit_digest.py --sub LocalLLaMA --sub selfhosted -t week -n 15
# Tìm kiếm
.venv/bin/python tools/reddit_digest.py --search "self hosted alternative to X" -t month -n 20
```
Lệnh in JSON gọn (title/score/comments/permalink/nội dung). Claude đọc rồi viết
digest tiếng Việt cho bạn — bạn không cần mở Reddit.

Giới hạn: app-only OAuth = 60 req/phút, đọc dữ liệu công khai (không đăng bài,
không sub riêng tư). Token tự làm mới trong Worker.
