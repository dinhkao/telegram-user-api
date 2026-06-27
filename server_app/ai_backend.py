from __future__ import annotations

import asyncio
import http.client
import json
import logging
import os
import subprocess
import ssl

from server_app.config import AI_BACKEND, FIREWORKS_API_KEY, FIREWORKS_MODEL, MAX_HISTORY, PI_MODEL, PI_SESSIONS_DIR, SYSTEM_PROMPT
from server_app.state import chat_histories

log = logging.getLogger("server")


async def ask_pi(chat_id: str, question: str) -> str:
    loop = asyncio.get_running_loop()
    safe_id = str(chat_id).replace("/", "_").replace(":", "_").lstrip("-")
    cmd = ["pi", "-p", "--model", PI_MODEL, "--session", str(PI_SESSIONS_DIR / f"{safe_id}.jsonl"), question]
    env = os.environ.copy()
    if FIREWORKS_API_KEY:
        env["FIREWORKS_API_KEY"] = FIREWORKS_API_KEY
    try:
        proc = await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180))
        out = (proc.stdout or "").strip() or (f"Error: {proc.stderr.strip()[:500]}" if proc.stderr else "")
        return out or "(empty response)"
    except subprocess.TimeoutExpired:
        return "Timeout: pi took too long."
    except Exception as e:
        return f"Error running pi: {e}"


def _ask_fireworks_sync(messages: list[dict]) -> str:
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("api.fireworks.ai", context=ctx, timeout=120)
    payload = json.dumps({"model": FIREWORKS_MODEL, "messages": messages, "max_tokens": 1024})
    conn.request("POST", "/inference/v1/chat/completions", payload, {"Authorization": f"Bearer {FIREWORKS_API_KEY}", "Content-Type": "application/json", "Accept": "application/json"})
    body = json.loads(conn.getresponse().read())
    conn.close()
    content = body["choices"][0]["message"]["content"].strip()
    return content.split("</thinking>")[-1].strip() if "</thinking>" in content else content


async def _ask_fireworks(chat_id: str, question: str) -> str:
    loop = asyncio.get_running_loop()
    history = chat_histories.setdefault(str(chat_id), [])
    history.append({"role": "user", "content": question})
    history[:] = history[-(MAX_HISTORY * 2):]
    try:
        answer = await loop.run_in_executor(None, _ask_fireworks_sync, [{"role": "system", "content": SYSTEM_PROMPT}] + history)
        history.append({"role": "assistant", "content": answer})
        return answer or "(empty response)"
    except Exception as e:
        history.pop()
        return f"Error: {e}"


async def ask_ai(chat_id: str, question: str) -> str:
    log.debug("Using %s backend for chat %s", AI_BACKEND, chat_id)
    return await ask_pi(chat_id, question) if AI_BACKEND == "pi" else await _ask_fireworks(chat_id, question)
