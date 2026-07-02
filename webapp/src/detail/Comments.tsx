// Khối trao đổi — bình luận web (web_comments, queueable offline) + log chat
// Telegram của topic (order_chat_messages, chỉ đọc), trộn theo thời gian.
import { useEffect, useMemo, useState } from "preact/hooks";
import { getJSON, postJSON, currentUser } from "../api";
import { fmtTime } from "../format";

type Item = { who: string; text: string; at: number; source: "web" | "tg" };

/** order_chat_messages.created_at là TEXT UTC 'YYYY-MM-DD HH:MM:SS' (sqlite
 *  datetime('now')), còn comment web là epoch giây — quy hết về epoch. */
function toEpoch(v: any): number {
  if (typeof v === "number") return v;
  const t = Date.parse(String(v || "").replace(" ", "T") + "Z");
  return isNaN(t) ? 0 : Math.floor(t / 1000);
}

export function Comments({ threadId, chatMessages }: { threadId: string; chatMessages: any[] }) {
  const [comments, setComments] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await getJSON(`/api/order/${threadId}/comments`);
      setComments(r.comments || []);
    } catch {
      /* offline không có cache thì thôi */
    }
  };
  useEffect(() => {
    load();
  }, [threadId]);

  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    try {
      const r = await postJSON(`/api/order/${threadId}/comments`, { text: t }, { queueable: true });
      setText("");
      if (r._queued) {
        const user = currentUser();
        setComments((p) => [...p, { username: user?.username || "?", text: t, created_at: Math.floor(Date.now() / 1000), _queued: true }]);
      } else {
        // server trả comment vừa tạo — append thẳng, khỏi refetch cả danh sách
        setComments((p) => [...p, r.comment]);
      }
    } catch (ex: any) {
      alert(ex.message);
    } finally {
      setBusy(false);
    }
  };

  // useMemo: không re-sort cả log chat dài theo từng phím gõ vào ô comment
  const items: Item[] = useMemo(
    () =>
      [
        ...comments.map((c): Item => ({ who: c.username, text: c.text, at: toEpoch(c.created_at), source: "web" })),
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
          <li key={i} class={it.source === "web" ? "comment web" : "comment tg"}>
            <div class="muted small">
              {it.source === "tg" ? "✈️ " : "💬 "}
              {it.who} · {fmtTime(it.at)}
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
