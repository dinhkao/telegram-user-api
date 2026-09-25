// Khối trao đổi — bình luận web (web_comments, queueable offline) + log chat
// Telegram của topic (order_chat_messages, chỉ đọc), trộn theo thời gian.
// `topic` (chỉ đơn hàng): khung trao đổi RIÊNG đặt ở 1 khu của trang chi tiết đơn
// (hoá đơn / xuất kho / giao hàng) — CÙNG luồng với khung chính, chỉ lọc theo topic và
// gửi kèm topic; khung chính hiện tất cả, tin có topic mang nhãn bấm nhảy tới khu đó.
import { useEffect, useMemo, useState } from "preact/hooks";
import { getJSON, postJSON, delJSON, currentUser } from "../api";
import { fmtTime } from "../format";
import { toast, confirmDialog } from "../ui/feedback";
import { onRealtime, eventMatchesBase } from "../realtime";
import { Icon } from "../ui/Icon";

type Item = { who: string; text: string; at: number; source: "web" | "tg"; id?: number; topic?: string | null };

export type CommentTopic = "hoa_don" | "xuat_kho" | "giao_hang";
const TOPIC_LABEL: Record<string, string> = { hoa_don: "Hoá đơn", xuat_kho: "Xuất kho", giao_hang: "Giao hàng" };
// Khu tương ứng trên trang chi tiết đơn (id phần tử) — nhãn ở khung chính bấm là cuộn tới
const TOPIC_ANCHOR: Record<string, string> = { hoa_don: "od-invoice", xuat_kho: "od-stock", giao_hang: "task-giao_hang" };

// Nhiều khung trên CÙNG trang (chính + 3 khu) cùng base → gộp 1 request đang bay
const inflight = new Map<string, Promise<any>>();
function fetchComments(base: string): Promise<any> {
  let p = inflight.get(base);
  if (!p) {
    p = getJSON(`${base}/comments`).finally(() => inflight.delete(base));
    inflight.set(base, p);
  }
  return p;
}

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

/** allowPin=false → ẩn nút 📢 ghim bảng tin. Bảng tin hiện cho MỌI người dùng nên
 *  luồng trao đổi về tiền lương (scope worker_moc) không được có nút này. */
export function Comments({ base, chatMessages = [], allowPin = true, topic }: {
  base: string; chatMessages?: any[]; allowPin?: boolean; topic?: CommentTopic;
}) {
  const [comments, setComments] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await fetchComments(base);
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
      const r = await postJSON(`${base}/comments`, topic ? { text: t, topic } : { text: t }, { queueable: true });
      setText("");
      if (r._queued) {
        const user = currentUser();
        setComments((p) => [...p, { username: user?.username || "?", text: t, created_at: Math.floor(Date.now() / 1000), topic: topic || null, _queued: true }]);
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

  // Ghim/gỡ bình luận trên banner chạy chữ (24h, nền đỏ) — nút 📢 là TOGGLE:
  // đang ghim (khớp text+href trong /api/banner/pins) thì bấm lần nữa để gỡ.
  const [pins, setPins] = useState<{ id: number; text: string; href?: string }[]>([]);
  const loadPins = () => getJSON("/api/banner/pins", { cache: false }).then((d) => setPins(d.pins || [])).catch(() => {});
  useEffect(() => {
    if (!allowPin) return;   // không có nút ghim thì khỏi tải danh sách ghim
    loadPins();
    const off = onRealtime((e) => { if (e.type === "banner_changed") loadPins(); });
    return () => off();
  }, [allowPin]);
  const pinOf = (it: Item) =>
    pins.find((p) => (p.href || "").split("?")[0] === hrefFromBase(base) && p.text === `${it.who}: ${it.text}`);
  const togglePin = async (it: Item) => {
    const cur = pinOf(it);
    try {
      if (cur) {
        if (!(await confirmDialog("Gỡ khỏi bảng tin?", { okLabel: "Gỡ", danger: true }))) return;
        await delJSON(`/api/banner/pin/${cur.id}`);
        toast("Đã gỡ khỏi bảng tin", "ok");
      } else {
        if (!(await confirmDialog(`Đưa lên bảng tin 24 giờ?\n“${it.text}”`, { okLabel: "Đưa lên" }))) return;
        // Comment web có id → kèm ?focus để bấm dòng trên banner cuộn thẳng tới comment
        const href = hrefFromBase(base) + (it.source === "web" && it.id ? `?focus=comment:${it.id}` : "");
        await postJSON("/api/banner/pin", { text: `${it.who}: ${it.text}`, href });
        toast("📢 Đã đưa lên bảng tin (24h)", "ok");
      }
      loadPins();
    } catch (ex: any) { toast(ex.message, "err"); }
  };

  // useMemo: không re-sort cả log chat dài theo từng phím gõ vào ô comment
  const items: Item[] = useMemo(
    () =>
      [
        ...comments
          .filter((c) => !topic || c.topic === topic)
          .map((c): Item => ({ who: c.username, text: c.text, at: toEpoch(c.created_at), source: "web", id: c.id, topic: c.topic })),
        ...(topic ? [] : chatMessages)
          .filter((m) => (m.text || "").trim())
          .map((m): Item => ({ who: m.sender_name || String(m.sender_id), text: m.text, at: toEpoch(m.created_at), source: "tg" })),
      ].sort((a, b) => a.at - b.at),
    [comments, chatMessages, topic]
  );

  const goTopic = (t: string) => document.getElementById(TOPIC_ANCHOR[t] || "")?.scrollIntoView({ behavior: "smooth", block: "center" });

  return (
    <div class={topic ? "topic-chat" : "card"}>
      {topic
        ? <div class="topic-chat-head"><Icon name="chat" size={13} /> Trao đổi về {TOPIC_LABEL[topic].toLowerCase()}{items.length ? ` (${items.length})` : ""}</div>
        : <b>Trao đổi</b>}
      <ul class="comment-list">
        {items.map((it, i) => (
          // Khung khu vực KHÔNG gắn id — khỏi trùng id với khung chính (?focus=comment:N)
          <li key={it.id ? `w${it.id}` : `t${it.source}-${it.at}-${i}`} id={it.id && !topic ? `comment-${it.id}` : undefined} class={it.source === "web" ? "comment web" : "comment tg"}>
            <div class="muted small cmt-head">
              {it.source === "tg" ? "✈️" : <Icon name="chat" size={12} />}{" "}
              {it.who} · {fmtTime(it.at)}
              {!topic && it.topic && TOPIC_LABEL[it.topic] && (
                <button class="cmt-topic" title="Tới khu này trên trang" onClick={() => goTopic(it.topic!)}>{TOPIC_LABEL[it.topic]}</button>
              )}
              {allowPin && (
                <button class={"cmt-pin" + (pinOf(it) ? " on" : "")}
                  title={pinOf(it) ? "Đang trên bảng tin — bấm để gỡ" : "Đưa lên bảng tin (24h)"}
                  onClick={() => togglePin(it)}>
                  <Icon name="megaphone" size={13} />
                </button>
              )}
            </div>
            <div>{it.text}</div>
          </li>
        ))}
        {!items.length && !topic && <li class="muted small">Chưa có trao đổi</li>}
      </ul>
      <div class="row">
        <input placeholder={topic ? `Trao đổi về ${TOPIC_LABEL[topic].toLowerCase()}…` : "Viết bình luận…"} value={text} onInput={(e: any) => setText(e.target.value)} onKeyDown={(e: any) => e.key === "Enter" && send()} />
        <button class="btn primary" disabled={busy} onClick={send}>Gửi</button>
      </div>
    </div>
  );
}
