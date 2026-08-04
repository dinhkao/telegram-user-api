"""aiohttp middleware web_auth — gắn request["web_user"] từ token; chặn /api/* khi bật.

Luôn giải token nếu client gửi (Authorization: Bearer … hoặc ?token=) → attribution
chạy cả khi chưa bật chặn. Enforcement chỉ khi WEB_AUTH_ENABLED=true (server_app/config.py).
Miễn chặn: /api/auth/login, /api/tg/* (đã có X-API-Key riêng), OPTIONS, mọi đường
dẫn ngoài /api/ (pages/static/ws — gate ở phase sau), và LOOPBACK (bot role cùng
process gọi API qua localhost không token — bot_core/utils.py post_json).

⚠ TOKEN HỎNG/HẾT HẠN LUÔN LÀ 401 (`stale_token_401`), kể cả khi chưa bật chặn:
trước đây token hết hạn chỉ bị BỎ QUA im lặng → app vẫn chạy như khách vô danh,
mọi thao tác ghi `by=None` (giao hàng → "Két chưa rõ", việc không ai nhận, lịch sử
ghi IP thay vì tên). Client bắt 401 → đá về màn đăng nhập (webapp/src/api.ts::parse).
Dùng bởi: server_app/app_factory. Logic quyết định thuần: is_exempt/extract_token/
stale_token_401.
"""
from __future__ import annotations

import logging
import time

from aiohttp import web

from server_app.config import WEB_AUTH_ENABLED
from server_app.web_auth.secret import get_web_auth_secret
from server_app.web_auth.token import verify_token

_EXEMPT_EXACT = {"/api/auth/login", "/api/auth/me",
                 # collector chấm công: bearer token RIÊNG (không phải web token),
                 # check constant-time trong server_app/attendance_routes.py
                 "/api/attendance/events"}
_EXEMPT_PREFIXES = ("/api/tg/",)
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
# Đường được phép nhận token web hỏng mà KHÔNG bị 401 (xem stale_token_401):
# đang đăng nhập lại, hoặc header Authorization là bearer của hệ khác.
_STALE_TOKEN_OK = {"/api/auth/login", "/api/attendance/events"}


def is_exempt(method: str, path: str, remote: str | None = None) -> bool:
    """Request này có được miễn kiểm token không (logic thuần, unit-test)."""
    if method == "OPTIONS":
        return True
    if remote in _LOOPBACK:
        return True   # bot role nội bộ (cùng máy); Tailscale/LAN không bao giờ là loopback
    if not path.startswith("/api/"):
        return True
    if path in _EXEMPT_EXACT:
        return True
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


def stale_token_401(method: str, path: str) -> bool:
    """Client GỬI token nhưng token hỏng/hết hạn → có nên trả 401 không (thuần).

    KHÔNG dùng `is_exempt` vì nó miễn cả loopback — sau Tailscale serve thì MỌI
    request đều là 127.0.0.1, 401 sẽ không bao giờ bắn. Ở đây chỉ cần loại các
    đường dùng bearer/API-key RIÊNG (không phải token web) + đường đăng nhập:
    - /api/auth/login: đang đăng nhập lại thì token cũ hỏng là chuyện đương nhiên
    - /api/attendance/events: máy chấm công có ATTENDANCE_BEARER_TOKEN riêng
    - /api/tg/*: X-API-Key riêng
    Ngoài /api/ (trang tĩnh, /ws) không đụng — 401 từ REST đủ để client về login.
    """
    if method == "OPTIONS" or not path.startswith("/api/"):
        return False
    if path in _STALE_TOKEN_OK:
        return False
    return not any(path.startswith(p) for p in _EXEMPT_PREFIXES)


def extract_token(headers, query) -> str:
    """Lấy token từ header Bearer, không có thì ?token= (cho WebSocket)."""
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return (query.get("token") or "").strip()


# Token sống tới 30 ngày nhưng user bị KHOÁ (disabled) phải văng ngay — re-check cờ
# disabled mỗi request qua cache TTL 60s (khỏi 1 DB hit / request; login đã chặn
# disabled nhưng token cũ vẫn chạy nếu chỉ check lúc login).
_DISABLED_TTL = 60.0
_disabled_cache: dict[str, tuple[bool, float]] = {}

log = logging.getLogger("server")


def _user_disabled(username: str) -> bool:
    now = time.time()
    hit = _disabled_cache.get(username)
    if hit is not None and now - hit[1] < _DISABLED_TTL:
        return hit[0]
    try:
        from user_store import get_user
        u = get_user(username)
        disabled = (u is None) or bool(u.get("disabled"))   # user đã xoá → coi như khoá
    except Exception:
        disabled = False   # DB trục trặc → không khoá oan cả app
    _disabled_cache[username] = (disabled, now)
    return disabled


@web.middleware
async def web_auth_middleware(request: web.Request, handler):
    token = extract_token(request.headers, request.query)
    if token:
        username = verify_token(get_web_auth_secret(), token, now=int(time.time()))
        # user disabled = token vô hiệu (cùng đường với token sai)
        if username and not _user_disabled(username):
            request["web_user"] = username
        elif stale_token_401(request.method, request.path):
            # Có token mà không nhận ra được (hết hạn 30 ngày / bị khoá / sai chữ
            # ký) — KHÔNG được chạy tiếp như khách vô danh, nếu không mọi thao tác
            # sẽ mất tên người làm. Trả 401 để client về màn đăng nhập.
            log.info("web_auth: token hỏng/hết hạn → 401 %s %s", request.method, request.path)
            return web.json_response(
                {"ok": False, "error": "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại",
                 "code": "token_expired"}, status=401)
    if WEB_AUTH_ENABLED and not is_exempt(request.method, request.path, request.remote) and "web_user" not in request:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    from order_store.mutation_audit import reset_actor, set_actor
    actor = request.get("web_user") or request.remote or "Hệ thống"
    token = set_actor("web_user" if request.get("web_user") else "http_client", actor)
    try:
        return await handler(request)
    finally:
        reset_actor(token)
