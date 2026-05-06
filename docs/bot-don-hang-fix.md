# bot-don-hang: polling errors and port conflict

**Date:** 2026-05-05
**Commit:** `49b9e01` (bot-don-hang)

---

## Symptoms

Bot log showed repeated polling errors at startup:

```
Polling error: RequestError: Error: read ETIMEDOUT  { code: 'EFATAL' }
Polling error: RequestError: Error: read ECONNRESET  { code: 'EFATAL' }
[http] Port 3000 in use. Another bot-don-hang may already be running.
```

Bot appeared to crash or hang. HTTP endpoints (`/health`, `/api/product-codes`) were unreachable.

---

## Root Causes

Two independent issues:

### 1. Port 3000 silently fails

The HTTP server used `process.env.PORT || 3000`. final_telegram already binds port 3000, so `server.listen()` throws `EADDRINUSE`. The error handler only logs it — no fallback port, no exit. The HTTP server silently fails to start.

### 2. Polling error handler too narrow

The `polling_error` handler only triggered restart for 409 conflicts:

```js
bot.on('polling_error', async (err) => {
  const msg = String(err.message).toLowerCase();
  if (msg.includes('409') || msg.includes('terminated')) {
    // restart ...
  }
  // network errors (ETIMEDOUT, ECONNRESET) → logged only, no action
});
```

The `node-telegram-bot-api` v0.66.0 library retries network errors internally via `.finally()` loop, but if the error persists (sustained outage), the polling hangs with no recovery. The stale polling lock remains, preventing restart.

### 3. Concurrent restart race

During restart, the previous instance's long-poll TCP connection sometimes lingers at Telegram's end. The new instance gets a 409 `Conflict: terminated by other getUpdates request`, restarts, then fails to re-acquire the polling lock because the retry timer uses `unref()` — if the HTTP server also failed to bind (port conflict), the Node event loop has zero active handles and the process exits silently.

---

## Fixes

### Fix 1 — Separate HTTP port

Changed from `process.env.PORT || 3000` to `process.env.BOT_HTTP_PORT || 3002`:

```js
const PORT = Number(process.env.BOT_HTTP_PORT || 3002);
```

Port 3001 is used by `hono-app`, so default is 3002. Configurable via `.env` if needed.

### Fix 2 — Broad polling error recovery

Replaced the 409-only handler with streak-based recovery for all errors:

```js
let pollingErrorStreak = 0;
let pollingErrorStreakSince = 0;

bot.on('polling_error', async (err) => {
  const msg = String(err.message).toLowerCase();
  const code = String(err.code || '').toUpperCase();

  // 409: always restart with fresh lock
  if (msg.includes('409') || msg.includes('terminated')) {
    console.error('Polling conflict (409):', msg);
    try { await bot.stopPolling(); } catch (_) {}
    pollingActive = false;
    stopPollingHeartbeat();
    await releasePollingLock();
    pollingErrorStreak = 0;
    schedulePollingStart(POLLING_RETRY_MS);
    return;
  }

  // Network errors: track streak, restart if persistent
  const now = Date.now();
  if (!pollingErrorStreakSince || now - pollingErrorStreakSince > 120_000) {
    pollingErrorStreak = 0;
    pollingErrorStreakSince = now;
  }
  pollingErrorStreak++;
  console.error(`Polling error [streak=${pollingErrorStreak}] ${code}:`, msg);

  if (pollingErrorStreak >= 5) {
    console.error('Persistent polling errors — full restart with backoff');
    try { await bot.stopPolling(); } catch (_) {}
    pollingActive = false;
    stopPollingHeartbeat();
    await releasePollingLock();
    pollingErrorStreak = 0;
    pollingErrorStreakSince = 0;
    schedulePollingStart(POLLING_RETRY_MS * 3); // 30s backoff
  }
});
```

Logic:
- Transient blips (1–4 errors) are logged, library retries internally
- 5 consecutive errors within 2 minutes → full restart with 3x backoff
- 409 conflicts → immediate restart (unchanged from original)
- Error streak resets after 2 minutes of clean polling

---

## Verification

After fixes, bot starts cleanly:

```
HTTP API listening on :3002
Polling started. Waiting for /start <order_id>...
```

Health check:
```
$ curl http://localhost:3002/health
{"ok":true}
```

Product codes API:
```
$ curl http://localhost:3002/api/product-codes
{"ok":true,"codes":["K10LV87","K10LV85",...]}  // 30 codes
```
