#!/usr/bin/env python
"""Mồi khởi động server.py cho launchd (~/Library/LaunchAgents/com.letrang.telegram-user-api.plist).

Chạy tay thì vẫn `.venv/bin/python server.py` như cũ — file này chỉ dành cho lúc máy
tự khởi động.

Vì sao mồi bằng PYTHON chứ không phải shell: repo nằm trên ổ ngoài
`/Volumes/samwinchester`, và macOS (TCC) CHẶN tiến trình do launchd sinh ra ĐỌC nội
dung file trên ổ ngoài — `stat`/`exec` thì cho, `open()` để đọc thì "Operation not
permitted". Nên phải cấp Full Disk Access cho ĐÚNG MỘT binary, và binary đó bắt buộc
là python của app (nó mới là thứ phải đọc cả repo). Dùng bash làm vỏ thì lại phải cấp
quyền cho /bin/bash — rộng và bẩn.

Việc duy nhất ở đây: DỌN TIẾN TRÌNH server.py LẠC rồi exec server.py. macOS bật
SO_REUSEPORT nên 2 tiến trình CÙNG nghe được cổng 8090, chia nhau request giữa code cũ
và code mới (404 lúc được lúc không — đã dính 2026-07-16); launchd phải là chủ duy nhất.

Không cần vòng lặp chờ ổ mount: ổ chưa lên thì launchd exec hụt file này, thất bại,
rồi thử lại sau ThrottleInterval — bản thân launchd đã là vòng chờ.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Dòng lệnh ĐÚNG của server: <đường dẫn python> -u server.py (và chỉ vậy).
# ⚠ KHÔNG lọc bằng `pgrep -f server\.py` trần: mẫu đó khớp MỌI tiến trình có chữ
# "server.py" trong dòng lệnh — kể cả shell đang chạy lệnh kiểm tra, grep, hay editor
# mở file. Đã tự giết nhầm shell chẩn đoán lúc dựng job này (2026-09-13).
_SERVER_ARGS = re.compile(r"(^|/)[Pp]ython[0-9.]*\s+-u\s+server\.py\s*$")


def _stray_pids() -> list[int]:
    """PID của tiến trình ĐANG CHẠY server.py, khác tiến trình này."""
    me = os.getpid()
    try:
        out = subprocess.run(["/bin/ps", "-Ao", "pid=,args="],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        pid_s, _, args = line.strip().partition(" ")
        if not pid_s.isdigit() or int(pid_s) == me:
            continue
        if _SERVER_ARGS.search(args.strip()):
            pids.append(int(pid_s))
    return pids


def _kill_strays() -> None:
    pids = _stray_pids()
    if not pids:
        return
    # stderr chứ KHÔNG phải stdout: lúc này chưa _redirect_log(), plist chỉ đặt
    # StandardErrorPath — in ra stdout là launchd vứt thẳng, mất dấu vết.
    print(f"[launchd_boot] dọn server.py lạc: {pids}", file=sys.stderr, flush=True)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(10):                      # chờ nhả cổng 8090
        time.sleep(1)
        if not _stray_pids():
            return
    for pid in _stray_pids():                # lì thì ép
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(1)


def _redirect_log() -> None:
    """Đổ stdout/stderr vào app_nohup.log của repo — nơi mọi hướng dẫn soi lỗi trỏ tới.

    Phải do CHÍNH python mở (nó mới có Full Disk Access), không giao cho
    StandardOutPath của launchd: launchd mở hộ thì lại là danh tính khác, ổ ngoài chặn.
    Mở hỏng thì cứ chạy tiếp — log rơi về StandardErrorPath (ổ trong) còn hơn không lên.
    """
    try:
        fd = os.open(os.path.join(ROOT, "app_nohup.log"),
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except OSError as e:
        print(f"[launchd_boot] không mở được app_nohup.log: {e}", file=sys.stderr, flush=True)
        return
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)


def main() -> None:
    py = os.path.join(ROOT, ".venv", "bin", "python")
    if not os.access(py, os.X_OK):
        sys.exit(f"[launchd_boot] không thấy {py}")
    _kill_strays()
    _redirect_log()
    os.chdir(ROOT)
    # exec để launchd theo dõi ĐÚNG pid của server, không phải pid của mồi này.
    # ⚠ Phải exec CHÍNH binary đang chạy (.venv/bin/python → bin/python3.14) — đổi sang
    # binary khác là đổi danh tính TCC, mất luôn quyền đọc ổ ngoài vừa được cấp.
    os.execv(py, [py, "-u", "server.py"])


if __name__ == "__main__":
    main()
