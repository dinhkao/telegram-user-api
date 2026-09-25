// Service worker WEB PUSH (iPhone PWA "Thêm vào màn hình chính" + trình duyệt không có APK).
// Phục vụ ở /app/sw.js → scope /app/. KHÔNG cache gì (không có fetch handler) — chỉ nhận push.
// Payload từ server (server_app/webpush.py): {title, body, url, tag}.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : "" }; }
  // iOS BẮT BUỘC mỗi push phải hiện 1 thông báo (userVisibleOnly) — luôn showNotification.
  e.waitUntil(self.registration.showNotification(d.title || "Lê Trang Phát", {
    body: d.body || "",
    tag: d.tag || undefined,
    icon: "/app/icons/icon-192.png",
    badge: "/app/icons/icon-192.png",
    data: { url: d.url || "/app/" },
  }));
});

// Bấm thông báo → mở/đưa app lên trước và điều hướng tới đúng trang (đơn / thùng / phiếu…)
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "/app/", self.location.origin).href;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of wins) {
      if (c.url.startsWith(self.location.origin + "/app")) {
        c.postMessage({ type: "open", url });   // app tự đổi hash (navigate() không chắc có trên iOS)
        return c.focus();
      }
    }
    return self.clients.openWindow(url);
  })());
});
