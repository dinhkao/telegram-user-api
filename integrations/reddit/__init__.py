"""Reddit read-only integration.

Máy chủ (IP Viettel VN) bị Reddit chặn ở tầng mạng, nên MỌI truy cập Reddit đi
qua Cloudflare Worker proxy (worker.js, egress edge non-VN) bằng app-only OAuth.
- worker.js   : Cloudflare Worker (deploy 1 lần) — xem README.md
- client.py   : client Python gọi Worker, trả JSON đã chuẩn hoá
Config qua env: REDDIT_PROXY_URL, REDDIT_PROXY_SECRET.
"""
