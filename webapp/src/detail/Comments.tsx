// Khối trao đổi — bình luận web (web_comments, queueable offline) + log chat
// Telegram của topic (order_chat_messages, chỉ đọc), trộn theo thời gian.
import { useEffect, useMemo, useState } from "preact/hooks";
import { getJSON, postJSON, currentUser } from "../api";
import { fmtTime } from "../format";
import { toast, confirmDialog } from "../ui/feedback";
import { onRealtime, eventMatchesBase } from "../realtime";
import { Icon } from "../ui/Icon";

type Item = { who: string; text: string; at: number; source: "web" | "tg"; id?: number };

/** order_chat_messages.created_at là TEXT UTC 'YYYY-MM-DD HH:MM:SS' (sqlite
 *  datetime('now')), còn comment web là epoch giây — quy hết về epoch. */
function toEpoch(v: any): number {
  if (typeof v === "number") return v;
  const t = Date.parse(String(v || "").replace(" ", "T") + "Z");
  return isNaN(t) ? 0 : Math.floor(t / 1000);
}

// Link về trang nguồn từ base API — để bấm dòng ghim trên banner nhảy đúng chỗ
function hrefFromBase(b: string): string {
  let m = b.match(/\/api\/order\/(-?\d+)/);
  if (m) return `#/order/${m[1]}`;
  m = b.match(/\/api\/media\/box\/(\d+)/);
  if (m) return `#/thung/${m[1]}`;
  m = b.match(/\/api\/media\/production\/(-?\d+)/);
  if (m) return `#/san_xuat/${m[1]}`;
  return "";
}

export function Comments({ base, chatMessages = [] }: { base: string; chatMessages?: any[] }) {
  const [comments, setComments] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await getJSON(`${base}/comments`);
      setComments(r.comments || []);
    } catch {
      /* offline không có cache thì thôi */
    }
  };
  useEffect(() => {
    load();
  }, [base]);

  // Realtime: bình luận/ảnh của người khác trên CÙNG thực thể → tải lại
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => { if (eventMatchesBase(base, e)) { clearTimeout(t); t = setTimeout(load, 250); } });
    return () => { off(); clearTimeout(t); };
  }, [base]);

  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    try {
      const r = await postJSON(`${base}/comments`, { text: t }, { queueable: true });
      setText("");
      if (r._queued) {
        const user = currentUser();
        setComments((p) => [...p, { username: user?.username || "?", text: t, created_at: Math.floor(Date.now() / 1000), _queued: true }]);
      } else {
        // server trả comment vừa tạo — append thẳng, khỏi refetch cả danh sách
        setComments((p) => [...p, r.comment]);
      }
    } catch (ex: any) {
      toast(ex.message, "err");
    } finally {
      setBusy(false);
    }
  };

  // Ghim bình luận lên banner chạy chữ (24h, nền đỏ) — mọi máy thấy ngay (realtime)
  const pinToBanner = async (it: Item) => {
    if (!(await confirmDialog(`Đưa lên bảng tin 24 giờ?\n“${it.text}”`, { okLabel: "Đưa lên" }))) return;
    try {
      await postJSON("/api/banner/pin", { text: `${it.who}: ${it.text}`, href: hrefFromBase(base) });
      toast("📢 Đã đưa lên bảng tin (24h)", "ok");
    } catch (ex: any) { toast(ex.message, "err"); }
  };

  // useMemo: không re-sort cả log chat dài theo từng phím gõ vào ô comment
  const items: Item[] = useMemo(
    () =>
      [
        ...comments.map((c): Item => ({ who: c.username, text: c.text, at: toEpoch(c.created_at), source: "web", id: c.id })),
        ...chatMessages
          .filter((m) => (m.text || "").trim())
          .map((m): Item => ({ who: m.sender_name || String(m.sender_id), text: m.text, at: toEpoch(m.created_at), source: "tg" })),
      ].sort((a, b) => a.at - b.at),
    [comments, chatMessages]
  );

  return (
    <div class="card">
      <b>Trao đổi</b>
      <ul class="comment-list">
        {items.map((it, i) => (
          <li key={it.id ? `w${it.id}` : `t${it.source}-${it.at}-${i}`} id={it.id ? `comment-${it.id}` : undefined} class={it.source === "web" ? "comment web" : "comment tg"}>
            <div class="muted small cmt-head">
              {it.source === "tg" ? "✈️" : <Icon name="chat" size={12} />}{" "}
              {it.who} · {fmtTime(it.at)}
              <button class="cmt-pin" title="Đưa lên bảng tin (24h)" onClick={() => pinToBanner(it)}>
                <Icon name="megaphone" size={13} />
              </button>
            </div>
            <div>{it.text}</div>
          </li>
        ))}
        {!items.length && <li class="muted small">Chưa có trao đổi</li>}
      </ul>
      <div class="row">
        <input placeholder="Viết bình luận…" value={text} onInput={(e: any) => setText(e.target.value)} onKeyDown={(e: any) => e.key === "Enter" && send()} />
        <button class="btn primary" disabled={busy} onClick={send}>Gửi</button>
      </div>
    </div>
  );
}
