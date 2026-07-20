"""Client Reddit read-only — gọi Cloudflare Worker proxy (worker.js), KHÔNG gọi
reddit.com trực tiếp (IP máy bị chặn). Trả về post/bình luận đã chuẩn hoá gọn để
tổng hợp digest.

Config (env):
  REDDIT_PROXY_URL     — vd https://letrang-reddit.<acc>.workers.dev  (bắt buộc)
  REDDIT_PROXY_SECRET  — khớp PROXY_SECRET của Worker                 (bắt buộc)

Dùng stdlib urllib (không thêm dependency). Đồng bộ — đủ cho fetch định kỳ / CLI.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class RedditProxyError(RuntimeError):
    pass


def _base() -> str:
    url = os.getenv("REDDIT_PROXY_URL", "").rstrip("/")
    if not url:
        raise RedditProxyError("Chưa đặt REDDIT_PROXY_URL (URL Cloudflare Worker).")
    return url


def _get(path: str, params: dict[str, Any] | None = None, timeout: float = 20) -> Any:
    qs = ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ""
    req = urllib.request.Request(_base() + path + qs)
    secret = os.getenv("REDDIT_PROXY_SECRET", "")
    if secret:
        req.add_header("x-proxy-secret", secret)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RedditProxyError(f"Worker {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RedditProxyError(f"Không gọi được Worker: {e}") from e
    # Cloudflare "Blocked" trả HTML → không phải JSON: báo rõ để smoke-test thấy.
    if raw.lstrip()[:1] not in "{[":
        raise RedditProxyError(f"Trả về KHÔNG phải JSON (có thể bị chặn): {raw[:160]}")
    return json.loads(raw)


def _norm_post(d: dict[str, Any]) -> dict[str, Any]:
    p = d.get("data", d)
    body = (p.get("selftext") or "").strip()
    return {
        "id": p.get("id"),
        "subreddit": p.get("subreddit"),
        "title": p.get("title"),
        "score": p.get("score"),
        "num_comments": p.get("num_comments"),
        "author": p.get("author"),
        "created_utc": p.get("created_utc"),
        "permalink": "https://reddit.com" + (p.get("permalink") or ""),
        "url": p.get("url"),
        "selftext": body[:1200] + ("…" if len(body) > 1200 else ""),
        "flair": p.get("link_flair_text"),
        "over_18": p.get("over_18"),
    }


def browse(subreddit: str, sort: str = "top", t: str = "week", limit: int = 25) -> list[dict[str, Any]]:
    """Lấy post 1 subreddit. sort: hot|new|top|rising. t: hour|day|week|month|year|all."""
    data = _get(f"/r/{urllib.parse.quote(subreddit)}/{sort}", {"t": t, "limit": limit, "raw_json": 1})
    return [_norm_post(c) for c in data.get("data", {}).get("children", [])]


def search(query: str, subreddits: list[str] | None = None, sort: str = "relevance",
           t: str = "all", limit: int = 25) -> list[dict[str, Any]]:
    """Tìm post. subreddits=None → toàn Reddit; nếu chỉ 1 sub thì tìm trong sub đó."""
    if subreddits and len(subreddits) == 1:
        path = f"/r/{urllib.parse.quote(subreddits[0])}/search"
        params = {"q": query, "restrict_sr": 1, "sort": sort, "t": t, "limit": limit, "raw_json": 1}
    else:
        path = "/search"
        q = query if not subreddits else query + " " + " ".join(f"subreddit:{s}" for s in subreddits)
        params = {"q": q, "sort": sort, "t": t, "limit": limit, "raw_json": 1}
    data = _get(path, params)
    return [_norm_post(c) for c in data.get("data", {}).get("children", [])]


def comments(subreddit: str, post_id: str, limit: int = 20, depth: int = 3) -> dict[str, Any]:
    """Lấy post + bình luận top. Trả {post, comments:[{author,score,body}]}."""
    data = _get(f"/r/{urllib.parse.quote(subreddit)}/comments/{urllib.parse.quote(post_id)}",
                {"limit": limit, "depth": depth, "sort": "top", "raw_json": 1})
    post = _norm_post(data[0]["data"]["children"][0]) if data and data[0].get("data") else {}
    out: list[dict[str, Any]] = []

    def walk(children: list[dict[str, Any]]):
        for c in children:
            if c.get("kind") != "t1":
                continue
            cd = c.get("data", {})
            b = (cd.get("body") or "").strip()
            if b:
                out.append({"author": cd.get("author"), "score": cd.get("score"),
                            "body": b[:600] + ("…" if len(b) > 600 else "")})
            replies = cd.get("replies")
            if isinstance(replies, dict):
                walk(replies.get("data", {}).get("children", []))

    if len(data) > 1 and data[1].get("data"):
        walk(data[1]["data"]["children"])
    return {"post": post, "comments": out[:limit]}


def health() -> bool:
    try:
        req = urllib.request.Request(_base() + "/health")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode().strip() == "ok"
    except Exception:
        return False
