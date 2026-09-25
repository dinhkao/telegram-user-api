// Khối "Thông báo trên máy này" ở ⚙️ Cài đặt (#/login) — Web Push cho iPhone/trình duyệt
// (webPush.ts). Trong APK Android thì ẩn (APK nhận push qua FCM). iPhone chưa cài lên màn
// hình chính → hướng dẫn từng bước. WebPushNudge = dải nhắc trên đầu app cho iPhone chưa bật.
import { useEffect, useState } from "preact/hooks";
import { enableWebPush, isIOS, sendTestWebPush, webPushState, type WebPushState } from "../webPush";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";

function InstallGuide() {
  return (
    <ol class="wp-steps">
      <li>Mở trang này bằng <b>Safari</b>, bấm nút <b>Chia sẻ</b> (ô vuông có mũi tên lên).</li>
      <li>Chọn <b>“Thêm vào MH chính”</b> → <b>Thêm</b>.</li>
      <li>Mở app <b>“Đơn hàng”</b> vừa hiện trên màn hình chính, <b>đăng nhập lại</b>.</li>
      <li>Vào <b>⚙️ Cài đặt</b> → bấm <b>🔔 Bật thông báo</b> → <b>Cho phép</b>.</li>
    </ol>
  );
}

export function WebPushCard() {
  const [st, setSt] = useState<WebPushState | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => webPushState().then(setSt);
  useEffect(() => { refresh(); }, []);
  if (!st || st === "apk") return null;

  const enable = async () => {
    setBusy(true);
    try { await enableWebPush(); toast("🔔 Đã bật thông báo trên máy này", "ok"); }
    catch (e: any) { toast(e?.message || "Chưa bật được", "err"); }
    finally { setBusy(false); refresh(); }
  };
  const test = async () => {
    setBusy(true);
    try { toast(await sendTestWebPush(), "ok"); } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(false); }
  };

  return (
    <div class="card wp-card">
      <label class="card-label"><Icon name="bell" size={15} /> Thông báo trên máy này</label>
      {st === "on" && (
        <>
          <p class="t-ok">✅ Đã bật — máy này nhận thông báo đơn, bình luận, thanh toán…</p>
          <button class="btn" disabled={busy} onClick={test}>Gửi thử 1 thông báo</button>
        </>
      )}
      {st === "off" && (
        <>
          <p class="muted small">Bật để nhận thông báo ngay cả khi không mở app.</p>
          <button class="btn primary block" disabled={busy} onClick={enable}>🔔 Bật thông báo</button>
        </>
      )}
      {st === "denied" && (
        <p class="t-warn small">Máy đã <b>chặn</b> thông báo của app. Vào <b>Cài đặt</b> của máy → <b>Thông báo</b> →
          <b> Đơn hàng</b> → bật <b>Cho phép thông báo</b>, rồi mở lại app.</p>
      )}
      {st === "need-install" && (
        <>
          <p class="small">iPhone chỉ nhận thông báo khi app được <b>thêm vào màn hình chính</b>:</p>
          <InstallGuide />
        </>
      )}
      {st === "unsupported" && (
        <p class="muted small">{isIOS()
          ? "iPhone cần iOS 16.4 trở lên để nhận thông báo — vào Cài đặt → Cài đặt chung → Cập nhật phần mềm."
          : "Trình duyệt này không hỗ trợ thông báo."}</p>
      )}
    </div>
  );
}

/** Dải nhắc trên đầu app: CHỈ iPhone (ngoài APK) chưa bật thông báo; ẩn 3 ngày khi bấm ✕. */
export function WebPushNudge() {
  const [st, setSt] = useState<WebPushState | null>(null);
  const KEY = "wp_nudge_hide_until";
  const hidden = () => { try { return Number(localStorage.getItem(KEY) || 0) > Date.now(); } catch { return false; } };
  useEffect(() => { if (isIOS() && !hidden()) webPushState().then(setSt); }, []);
  if (!st || st === "on" || st === "apk" || st === "unsupported") return null;
  const hide = (e: Event) => {
    e.preventDefault();
    try { localStorage.setItem(KEY, String(Date.now() + 3 * 86400000)); } catch { /* ignore */ }
    setSt(null);
  };
  return (
    <a class="wp-nudge" href="#/login">
      <Icon name="bell" size={15} />
      <span>{st === "need-install" ? "Thêm app vào màn hình chính để nhận thông báo" : "Bật thông báo trên iPhone này"}</span>
      <button class="wp-nudge-x" aria-label="Ẩn" onClick={hide}>✕</button>
    </a>
  );
}
