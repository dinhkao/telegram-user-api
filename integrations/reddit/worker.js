// Cloudflare Worker — Reddit read-only OAuth proxy.
//
// LÝ DO TỒN TẠI: máy chủ (IP Viettel VN, AS7552) bị Reddit/Cloudflare chặn cả
// endpoint ẩn danh .json LẪN oauth.reddit.com (403 trang "Blocked by network
// security"). Worker chạy ở edge Cloudflare (IP non-VN) nên qua được cổng chặn.
// Luồng: Mac (server.py) → https://<name>.workers.dev/... → oauth.reddit.com.
//
// XÁC THỰC: app-only OAuth (client_credentials, scope read) — đọc được subreddit
// công khai + bình luận, 60 req/phút. KHÔNG cần username/password.
//
// SECRETS (đặt bằng `wrangler secret put` hoặc Dashboard → Settings → Variables):
//   REDDIT_CLIENT_ID      — client id của "script" app (reddit.com/prefs/apps)
//   REDDIT_CLIENT_SECRET  — secret của app đó
//   PROXY_SECRET          — chuỗi ngẫu nhiên tự đặt; client PHẢI gửi header
//                           x-proxy-secret khớp (chặn người lạ xài proxy của bạn)
//   REDDIT_UA (tuỳ chọn)  — User-Agent, mặc định "letrang-reddit/0.1 by u/letrang"
//
// DÙNG: GET /r/<sub>/top?t=week&limit=25   ·  /search?q=...  ·  /health
//   (đường dẫn + query được chuyển thẳng sang oauth.reddit.com)

let _tok = null;          // token app-only, cache trong isolate
let _exp = 0;             // epoch ms hết hạn (đã trừ hao 5 phút)

async function getToken(env) {
  const now = Date.now();
  if (_tok && now < _exp) return _tok;
  const basic = btoa(`${env.REDDIT_CLIENT_ID}:${env.REDDIT_CLIENT_SECRET}`);
  const ua = env.REDDIT_UA || "letrang-reddit/0.1 by u/letrang";
  const r = await fetch("https://www.reddit.com/api/v1/access_token", {
    method: "POST",
    headers: {
      "Authorization": `Basic ${basic}`,
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": ua,
    },
    body: "grant_type=client_credentials",
  });
  if (!r.ok) throw new Error(`token ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const j = await r.json();
  _tok = j.access_token;
  _exp = now + Math.max(0, (j.expires_in || 3600) - 300) * 1000;
  return _tok;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/health") return new Response("ok", { status: 200 });

    // Cổng bảo vệ: bắt buộc đúng shared secret (nếu đã đặt).
    if (env.PROXY_SECRET && req.headers.get("x-proxy-secret") !== env.PROXY_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    try {
      const tok = await getToken(env);
      const ua = env.REDDIT_UA || "letrang-reddit/0.1 by u/letrang";
      const target = `https://oauth.reddit.com${url.pathname}${url.search}`;
      const rr = await fetch(target, {
        headers: { "Authorization": `Bearer ${tok}`, "User-Agent": ua },
      });
      const body = await rr.text();
      return new Response(body, {
        status: rr.status,
        headers: {
          "content-type": rr.headers.get("content-type") || "application/json",
          "x-reddit-status": String(rr.status),
        },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: String(e) }), {
        status: 502,
        headers: { "content-type": "application/json" },
      });
    }
  },
};
