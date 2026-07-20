#!/usr/bin/env python3
"""CLI lấy dữ liệu Reddit (qua Cloudflare Worker proxy) → in JSON gọn để Claude
tổng hợp digest tiếng Việt. KHÔNG tự viết văn — chỉ gom post/bình luận sạch.

Ví dụ:
  .venv/bin/python tools/reddit_digest.py --sub LocalLLaMA --sub selfhosted -t week -n 15
  .venv/bin/python tools/reddit_digest.py --search "claude code vs cursor" -t month -n 20
  .venv/bin/python tools/reddit_digest.py --smoke      # kiểm tra proxy có qua được Reddit

Cần env: REDDIT_PROXY_URL, REDDIT_PROXY_SECRET.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])
from integrations.reddit import client  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Lấy Reddit qua Worker proxy")
    ap.add_argument("--sub", action="append", default=[], help="subreddit (lặp nhiều lần)")
    ap.add_argument("--search", help="từ khoá tìm kiếm (thay cho --sub)")
    ap.add_argument("--sort", default=None, help="hot|new|top|rising | relevance (search)")
    ap.add_argument("-t", "--time", default="week", help="hour|day|week|month|year|all")
    ap.add_argument("-n", "--limit", type=int, default=15)
    ap.add_argument("--smoke", action="store_true", help="chỉ smoke-test proxy rồi thoát")
    args = ap.parse_args()

    if args.smoke:
        ok = client.health()
        print(f"health: {'OK' if ok else 'FAIL'}")
        try:
            posts = client.browse("programming", sort="top", t="week", limit=2)
            print(f"reddit fetch: OK — {len(posts)} post (proxy QUA được cổng chặn)")
            print(json.dumps(posts[:1], ensure_ascii=False, indent=2))
            return 0
        except Exception as e:
            print(f"reddit fetch: FAIL — {e}", file=sys.stderr)
            return 1

    try:
        if args.search:
            posts = client.search(args.search, subreddits=args.sub or None,
                                  sort=args.sort or "relevance", t=args.time, limit=args.limit)
        elif args.sub:
            posts = []
            for s in args.sub:
                posts += client.browse(s, sort=args.sort or "top", t=args.time, limit=args.limit)
        else:
            ap.error("cần --sub hoặc --search")
            return 2
    except Exception as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 1

    posts.sort(key=lambda p: (p.get("score") or 0), reverse=True)
    print(json.dumps({"count": len(posts), "posts": posts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
