// Card "Cập nhật ứng dụng" ở trang cài đặt.
// APK mới (có cầu JS window.AndroidApp) → cập nhật 1 CHẠM: bấm gọi native tải APK
// + mở trình cài (chỉ còn 1 hộp xác nhận của Android), và đọc ĐÚNG phiên bản đang
// cài để so "mới nhất hay chưa".
// APK cũ / trình duyệt (không có cầu) → fallback: tải /app/update/app.apk + proxy
// "Đã cài xong" (lưu versionCode vào localStorage).
import { useEffect, useState } from "preact/hooks";
import { getApkVersion, forceReloadAll, currentUser, type ApkVersion } from "../api";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { ErrorState } from "../ui/states";

const LS_KEY = "apk_installed_vc"; // proxy khi KHÔNG có cầu native

// Cầu JS do APK tiêm (chỉ có ở bản APK mới)
const bridge: any = (typeof window !== "undefined") ? (window as any).AndroidApp : undefined;
function bridgeVersion(): number | null {
  try { return bridge?.versionCode ? Number(bridge.versionCode()) : null; } catch { return null; }
}

export function AppUpdate() {
  const [latest, setLatest] = useState<ApkVersion | null>(null);
  const [checking, setChecking] = useState(false);
  const [err, setErr] = useState("");
  // Bản đang cài: ưu tiên cầu native (chính xác), nếu không có → proxy localStorage
  const [installed, setInstalled] = useState<number | null>(() => {
    const nv = bridgeVersion();
    if (nv != null) return nv;
    const v = localStorage.getItem(LS_KEY);
    return v ? Number(v) : null;
  });

  const check = async () => {
    setChecking(true); setErr("");
    try {
      setLatest(await getApkVersion());
    } catch (e: any) { setErr(e.message); } finally { setChecking(false); }
  };

  useEffect(() => { check(); }, []);

  const markInstalled = () => {
    if (!latest) return;
    localStorage.setItem(LS_KEY, String(latest.versionCode));
    setInstalled(latest.versionCode);
  };

  const doForceReload = async () => {
    if (!(await confirmDialog("Buộc MỌI máy đang mở tải lại web ngay?", { okLabel: "Tải lại hết" }))) return;
    try {
      const r = await forceReloadAll();
      toast(`Đã gửi tín hiệu tải lại tới ${r.clients} máy đang kết nối.`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi gửi tín hiệu", "err"); }
  };

  const hasBridge = !!bridge?.updateNow;
  const hasBuild = !!latest && latest.versionCode > 0;
  const upToDate = hasBuild && installed != null && installed >= latest!.versionCode;
  const outdated = hasBuild && installed != null && installed < latest!.versionCode;

  return (
    <div class="card">
      <div class="row space">
        <b><Icon name="download" size={16} /> Cập nhật ứng dụng</b>
        <button class="btn small" disabled={checking} onClick={check}>{checking ? "Đang kiểm tra…" : <><Icon name="refresh" size={14} /> Kiểm tra</>}</button>
      </div>

      {err && <ErrorState msg={err} />}

      {!latest ? (
        !err && <p class="muted small">Đang kiểm tra…</p>
      ) : !hasBuild ? (
        <p class="muted small">Chưa có bản cài đặt nào trên máy chủ.</p>
      ) : (
        <>
          <p class="muted small">
            Bản mới nhất: <b>{latest.versionName || `v${latest.versionCode}`}</b> (#{latest.versionCode})
            {installed != null && <> · Đang cài: v{installed}</>}
          </p>
          {upToDate && <p class="paid-ok"><Icon name="check" size={14} /> Bạn đang dùng bản mới nhất.</p>}
          {outdated && <p class="owe"><Icon name="bell" size={14} /> Có bản mới hơn bản bạn đang cài!</p>}
          {installed == null && !hasBridge && <p class="muted small">Chưa rõ bản đang cài — tải & cài rồi bấm "Đã cài xong".</p>}

          {hasBridge ? (
            // 1 chạm: native tải APK + mở trình cài (chỉ còn hộp xác nhận Android)
            <button class="btn primary wide" onClick={() => { try { bridge.updateNow(); } catch { /* ignore */ } }}>
              <Icon name="download" size={16} /> Cập nhật ngay (1 chạm)
            </button>
          ) : (
            <div class="row">
              <a class="btn primary" href="/app/update/app.apk"><Icon name="download" size={16} /> Tải & cài bản mới</a>
              <button class="btn" onClick={markInstalled}><Icon name="check" size={16} /> Đã cài xong bản này</button>
            </div>
          )}
        </>
      )}

      {currentUser()?.role === "admin" && (
        <div style={{ marginTop: "12px", paddingTop: "10px", borderTop: "1px solid var(--border)" }}>
          <button class="btn small block" onClick={doForceReload}>
            <Icon name="refresh" size={15} /> Buộc mọi máy tải lại web
          </button>
          <p class="muted small" style={{ margin: "5px 0 0" }}>
            Gửi tín hiệu tải lại tới mọi máy ĐANG MỞ (để lấy giao diện mới). Máy đang dùng
            bản cũ chưa có tính năng này thì cần mở lại app 1 lần.
          </p>
        </div>
      )}
    </div>
  );
}
