"""Test: chromium-1223 (148.0.7778.96) headless shell on macOS 15."""
from playwright.sync_api import sync_playwright

EXE = "/Users/duydinh0225/Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-arm64/chrome-headless-shell"

print(f"Testing chromium-1223 headless shell...")
p = sync_playwright().start()
try:
    b = p.chromium.launch(
        headless=True,
        executable_path=EXE,
        args=["--no-sandbox", "--disable-gpu"],
    )
    pg = b.new_page()
    pg.set_content("<h1>chromium-1223 WORKS!</h1>")
    pg.screenshot(path="/tmp/test_1223.png", full_page=True)
    pg.close()
    b.close()
    print("SUCCESS — chromium-1223 works on macOS 15!")
except Exception as e:
    msg = str(e)
    if "SEGV" in msg or "signal 11" in msg:
        print("FAILED: SIGSEGV (still crashes)")
    elif "EPERM" in msg or "not permitted" in msg:
        print("FAILED: sandbox permission error")
    else:
        print(f"FAILED: {type(e).__name__}: {msg[:300]}")
finally:
    p.stop()
