// Trung tâm thông báo trong app — chuông 🔔 + panel danh sách. Đồng bộ với FCM:
// server ghi 1 notification row CÙNG LÚC push FCM (server_app/notify.py) nên list ở
// đây khớp push. Realtime notif_added → cập nhật tức thì. Chưa đọc = id > seen (lưu
// localStorage). Bấm 1 thông báo → deep-link #/order/<id>?focus=<type>:<id>.
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { listNotifications, type Notif } from "./api";
import { onRealtime } from "./realtime";
import { fmtRelative } from "./format";

const SEEN_KEY = "notif_seen_id";
const getSeen = (): number => { try { return Number(localStorage.getItem(SEEN_KEY) || "0") || 0; } catch { return 0; } };
const setSeen = (id: number) => { try { localStorage.setItem(SEEN_KEY, String(id)); } catch { /* im */ } };

const ICON: Record<string, string> = { comment: "💬", image: "🖼", order: "🆕", info: "🔔" };

export function NotifCenter() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notif[]>([]);
  const [seen, setSeenState] = useState<number>(getSeen());

  const load = async () => {
    try {
      const r = await listNotifications(30);
      setItems(r.notifications);
    } catch { /* im */ }
  };
  useEffect(() => { load(); }, []);

  // Realtime: thông báo mới → prepend (dedup), badge tự tăng
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "notif_added" && e.notif) {
        setItems((prev) => (prev.some((n) => n.id === e.notif.id) ? prev : [e.notif as Notif, ...prev].slice(0, 30)));
      } else if (e.type === "resync") {
        load();
      }
    });
  }, []);

  const maxId = items.length ? items[0].id : 0;
  const unread = items.filter((n) => n.id > seen).length;

  const openPanel = () => {
    setOpen(true);
    if (maxId > seen) { setSeen(maxId); setSeenState(maxId); }   // mở = coi như đã xem
  };

  const go = (n: Notif) => {
    setOpen(false);
    if (n.thread_id) {
      // KHÔNG encode: main.tsx bắt focus=<type>:<id> với dấu ':' nguyên; encodeURIComponent
      // biến ':' → '%3A' làm regex trượt → không cuộn tới đích. n.focus toàn ký tự an toàn.
      const f = n.focus ? `?focus=${n.focus}` : "";
      window.location.hash = `#/order/${n.thread_id}${f}`;
    }
  };

  const panelRef = useRef<HTMLDivElement>(null);

  return (
    <>
      <button class="icon-btn notif-bell" title="Thông báo" onClick={openPanel}>
        🔔{unread > 0 && <span class="notif-badge">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && createPortal(
        <div class="modal-overlay" onClick={() => setOpen(false)}>
          <div class="modal-sheet notif-panel" ref={panelRef} onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head">🔔 Thông báo</div>
            {items.length === 0 ? (
              <div class="notif-empty muted small">Chưa có thông báo nào.</div>
            ) : (
              <ul class="notif-list">
                {items.map((n) => (
                  <li class={"notif-item" + (n.thread_id ? " tappable" : "")} key={n.id} onClick={() => go(n)}>
                    <span class="notif-ico">{ICON[n.type] || "🔔"}</span>
                    <div class="notif-body">
                      <div class="notif-title">{n.title}</div>
                      <div class="notif-text">{n.body}</div>
                      <div class="muted small">{fmtRelative(n.created_at)}</div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
