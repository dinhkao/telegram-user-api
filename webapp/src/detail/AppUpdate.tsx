// Card "Cập nhật ứng dụng" ở trang cài đặt — kiểm tra bản APK mới nhất trên máy
// chủ (/app/update/version.json) và tải về (/app/update/app.apk → Android hỏi cài).
// APK (WebView builder) KHÔNG báo phiên bản đang cài cho web → dùng proxy: sau khi
// cài xong người dùng bấm "Đã cài xong" để lưu versionCode vào localStorage, nhờ đó
// lần sau biết đang ở bản mới nhất hay chưa.
import { useEffect, useState } from "preact/hooks";
import { getApkVersion, type ApkVersion } from "../api";

const LS_KEY = "apk_installed_vc"; // versionCode người dùng đánh dấu "đã cài"

export function AppUpdate() {
  const [latest, setLatest] = useState<ApkVersion | null>(null);
  const [checking, setChecking] = useState(false);
  const [err, setErr] = useState("");
  const [installed, setInstalled] = useState<number | null>(() => {
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

  const hasBuild = !!latest && latest.versionCode > 0;
  const upToDate = hasBuild && installed != null && installed >= latest!.versionCode;
  const outdated = hasBuild && installed != null && installed < latest!.versionCode;

  return (
    <div class="card">
      <div class="row space">
        <b>📲 Cập nhật ứng dụng</b>
        <button class="btn small" disabled={checking} onClick={check}>{checking ? "Đang kiểm tra…" : "🔄 Kiểm tra"}</button>
      </div>

      {err && <p class="error">{err}</p>}

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
          {upToDate && <p class="paid-ok">✅ Bạn đang dùng bản mới nhất.</p>}
          {outdated && <p class="owe">🔔 Có bản mới hơn bản bạn đang cài!</p>}
          {installed == null && <p class="muted small">Chưa rõ bản đang cài — tải & cài rồi bấm "Đã cài xong".</p>}
          <div class="row">
            <a class="btn primary" href="/app/update/app.apk">⬇️ Tải & cài bản mới</a>
            <button class="btn" onClick={markInstalled}>✔️ Đã cài xong bản này</button>
          </div>
        </>
      )}
    </div>
  );
}
