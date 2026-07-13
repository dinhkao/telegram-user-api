import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { Icon } from "../ui/Icon";
import { ErrorState, Loading, LoadingInline } from "../ui/states";
import { usePopupBack } from "../ui/usePopupBack";

type CameraAccount = { id: string; label: string; folder: string };
type CameraChannel = { id: string; label: string; folder: string };
type CameraImage = {
  id: string;
  account_id: string;
  account_label: string;
  channel: string;
  name: string;
  created_at?: string;
  width: number;
  height: number;
  bytes: number;
  thumbnail_url: string;
  preview_url: string;
  original_url: string;
};

// Snapshot gallery của lần xem gần nhất — sống ở module scope (pattern listCache của
// OrdersList) để quay lại trang là hiện ngay, refreshLatest chạy nền. Chỉ metadata
// (~1KB/ảnh, bounded theo số ảnh đã tải). KHÔNG cache khi đang lọc thời gian from/to.
let galleryCache: {
  account: string; channel: string;
  images: CameraImage[]; accounts: CameraAccount[]; channels: CameraChannel[];
  cursor: string | null; total: number; savedAt: number;
} | null = null;
const GALLERY_CACHE_TTL = 10 * 60_000;

// Formatter Intl tạo 1 lần — constructor đắt, timeLabel chạy cho từng ảnh mỗi render.
const dayFmt = new Intl.DateTimeFormat("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" });
const dateTimeFmt = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
});

const dayKey = (value?: string) => value ? value.slice(0, 10) : "unknown";
const dayLabel = (value?: string) => {
  if (!value) return "Không rõ ngày";
  const date = new Date(value);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(date, today)) return "Hôm nay";
  if (same(date, yesterday)) return "Hôm qua";
  return dayFmt.format(date);
};
const timeLabel = (value?: string) => value ? timeFmt.format(new Date(value)) : "";
const dateTimeLabel = (value: string) => dateTimeFmt.format(new Date(value));
const localInputValue = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

function CameraViewer({ images, start, onClose }: { images: CameraImage[]; start: number; onClose: () => void }) {
  const [index, setIndex] = useState(start);
  const [previewReady, setPreviewReady] = useState(false);
  const mediaRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const gesture = useRef({
    scale: 1, x: 0, y: 0, pointers: new Map<number, { x: number; y: number }>(),
    pinchDistance: 0, pinchScale: 1, lastX: 0, lastY: 0, lastTap: 0,
  });
  usePopupBack(true, onClose);

  const applyTransform = (animate = false) => {
    const media = mediaRef.current;
    if (!media) return;
    const state = gesture.current;
    media.style.transition = animate ? "transform .2s ease" : "none";
    media.style.transform = `translate3d(${state.x}px,${state.y}px,0) scale(${state.scale})`;
  };
  const resetZoom = (animate = false) => {
    Object.assign(gesture.current, { scale: 1, x: 0, y: 0, pinchDistance: 0 });
    applyTransform(animate);
  };
  const zoomBy = (factor: number) => {
    const state = gesture.current;
    state.scale = Math.min(8, Math.max(1, state.scale * factor));
    if (state.scale === 1) { state.x = 0; state.y = 0; }
    applyTransform(true);
  };
  const pointerDistance = () => {
    const points = [...gesture.current.pointers.values()];
    return points.length < 2 ? 0 : Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
  };
  const onPointerDown = (event: PointerEvent) => {
    if ((event.target as HTMLElement).closest(".camera-viewer-top, .camera-viewer-bottom")) return;
    overlayRef.current?.setPointerCapture(event.pointerId);
    const state = gesture.current;
    state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (state.pointers.size === 2) {
      state.pinchDistance = pointerDistance();
      state.pinchScale = state.scale;
    } else {
      state.lastX = event.clientX;
      state.lastY = event.clientY;
      const now = Date.now();
      if (now - state.lastTap < 300) {
        state.scale > 1.05 ? resetZoom(true) : zoomBy(2.5);
        state.lastTap = 0;
      } else state.lastTap = now;
    }
  };
  const onPointerMove = (event: PointerEvent) => {
    const state = gesture.current;
    if (!state.pointers.has(event.pointerId)) return;
    state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (state.pointers.size >= 2 && state.pinchDistance > 0) {
      state.scale = Math.min(8, Math.max(1, state.pinchScale * pointerDistance() / state.pinchDistance));
      applyTransform();
    } else if (state.scale > 1.01) {
      state.x += event.clientX - state.lastX;
      state.y += event.clientY - state.lastY;
      state.lastX = event.clientX;
      state.lastY = event.clientY;
      applyTransform();
    }
    event.preventDefault();
  };
  const onPointerUp = (event: PointerEvent) => {
    const state = gesture.current;
    state.pointers.delete(event.pointerId);
    if (state.pointers.size < 2) state.pinchDistance = 0;
    const remaining = [...state.pointers.values()][0];
    if (remaining) { state.lastX = remaining.x; state.lastY = remaining.y; }
    if (state.scale <= 1.01) resetZoom(true);
  };
  const onWheel = (event: WheelEvent) => {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 1.2 : 1 / 1.2);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1));
      if (event.key === "ArrowRight") setIndex((value) => Math.min(images.length - 1, value + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [images.length]);
  useEffect(() => { setPreviewReady(false); resetZoom(false); }, [index]);
  useEffect(() => {
    if (!previewReady) return;
    const timer = window.setTimeout(() => {
      for (const next of [images[index - 1], images[index + 1]]) {
        if (!next) continue;
        const preload = new Image();
        preload.decoding = "async";
        preload.src = next.preview_url;
      }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [previewReady, index, images.length]);
  const image = images[index];
  if (!image) return null;
  return (
    <div class="camera-viewer" ref={overlayRef} role="dialog" aria-modal="true" aria-label={`Ảnh ${image.name}`}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onWheel={onWheel}>
      <div class="camera-viewer-top">
        <span class="camera-viewer-source">{image.channel.replace("_", " ")} · {image.account_label}</span>
        <button class="camera-viewer-btn" onClick={() => zoomBy(1 / 1.4)} title="Thu nhỏ"><Icon name="minus" size={20} /></button>
        <button class="camera-viewer-btn" onClick={() => zoomBy(1.4)} title="Phóng to"><Icon name="plus" size={20} /></button>
        <a class="camera-viewer-btn" href={image.original_url} target="_blank" rel="noopener" title="Mở ảnh gốc"><Icon name="download" size={20} /></a>
        <button class="camera-viewer-btn" onClick={onClose} title="Đóng"><Icon name="close" size={22} /></button>
      </div>
      <div class="camera-viewer-media" ref={mediaRef}>
        <img class={previewReady ? "camera-viewer-placeholder hidden" : "camera-viewer-placeholder"}
          src={image.thumbnail_url} alt="" draggable={false} />
        <img class={previewReady ? "camera-viewer-img ready" : "camera-viewer-img"}
          src={image.preview_url} alt={image.name} draggable={false} onLoad={() => setPreviewReady(true)} />
      </div>
      {!previewReady && <span class="camera-viewer-loading"><i /> Đang làm nét…</span>}
      <div class="camera-viewer-bottom">
        <button class="camera-viewer-btn" disabled={index === 0} onClick={() => setIndex(index - 1)} title="Ảnh trước"><Icon name="back" size={22} /></button>
        <div class="camera-viewer-meta">
          <b>{index + 1} / {images.length}</b>
          <span>{timeLabel(image.created_at)} · {image.width}×{image.height}</span>
        </div>
        <button class="camera-viewer-btn" disabled={index === images.length - 1} onClick={() => setIndex(index + 1)} title="Ảnh sau"><Icon name="chevronRight" size={22} /></button>
      </div>
    </div>
  );
}

export function CameraGallery() {
  if (galleryCache && Date.now() - galleryCache.savedAt > GALLERY_CACHE_TTL) galleryCache = null;
  const cached = galleryCache; // useState chỉ đọc ở render đầu
  const [images, setImages] = useState<CameraImage[]>(cached?.images ?? []);
  const [accounts, setAccounts] = useState<CameraAccount[]>(cached?.accounts ?? []);
  const [channels, setChannels] = useState<CameraChannel[]>(cached?.channels ?? []);
  const [selectedAccount, setSelectedAccount] = useState(cached?.account ?? "");
  const [selectedChannel, setSelectedChannel] = useState(cached?.channel ?? "");
  const [cursor, setCursor] = useState<string | null>(cached?.cursor ?? null);
  const [total, setTotal] = useState(cached?.total ?? 0);
  const [loading, setLoading] = useState(!cached);
  const [more, setMore] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState(cached?.savedAt ?? 0);
  const [error, setError] = useState("");
  const [sourceErrors, setSourceErrors] = useState(0);
  const [viewer, setViewer] = useState<number | null>(null);
  const [rangeOpen, setRangeOpen] = useState(false);
  const [rangeFrom, setRangeFrom] = useState("");
  const [rangeTo, setRangeTo] = useState("");
  const [draftFrom, setDraftFrom] = useState("");
  const [draftTo, setDraftTo] = useState("");
  const [rangeError, setRangeError] = useState("");
  const requestId = useRef(0);
  const freshRequestId = useRef(0);
  const busyRef = useRef(true);
  busyRef.current = loading || more || syncing;
  const viewerRef = useRef(false);
  viewerRef.current = viewer !== null;
  const skipFirstLoad = useRef(!!cached);
  // Snapshot cho lần quay lại — ref cập nhật mỗi render, ghi cache khi unmount.
  const st = useRef({ images, accounts, channels, selectedAccount, selectedChannel, cursor, total, rangeFrom, rangeTo });
  st.current = { images, accounts, channels, selectedAccount, selectedChannel, cursor, total, rangeFrom, rangeTo };
  useEffect(() => () => {
    const s = st.current;
    if (s.rangeFrom || s.rangeTo) { galleryCache = null; return; } // đang xem lịch sử → lệch scroll-restore, bỏ cache
    if (!s.images.length) return;
    galleryCache = {
      account: s.selectedAccount, channel: s.selectedChannel,
      images: s.images, accounts: s.accounts, channels: s.channels,
      cursor: s.cursor, total: s.total, savedAt: Date.now(),
    };
  }, []);
  usePopupBack(rangeOpen, () => setRangeOpen(false));

  const addTimeRange = (query: URLSearchParams) => {
    if (rangeFrom) query.set("from", rangeFrom);
    if (rangeTo) query.set("to", rangeTo);
  };
  const openRange = () => {
    const now = new Date();
    const start = new Date(now); start.setHours(0, 0, 0, 0);
    setDraftFrom(rangeFrom ? localInputValue(new Date(rangeFrom)) : localInputValue(start));
    setDraftTo(rangeTo ? localInputValue(new Date(rangeTo)) : localInputValue(now));
    setRangeError("");
    setRangeOpen(true);
  };
  const applyRange = () => {
    if (!draftFrom || !draftTo) { setRangeError("Chọn đủ thời gian bắt đầu và kết thúc"); return; }
    const from = new Date(draftFrom), to = new Date(draftTo);
    if (!Number.isFinite(from.getTime()) || !Number.isFinite(to.getTime()) || from > to) {
      setRangeError("Thời gian bắt đầu phải trước thời gian kết thúc"); return;
    }
    setRangeFrom(from.toISOString());
    setRangeTo(to.toISOString());
    setRangeOpen(false);
  };
  const clearRange = () => {
    setRangeFrom(""); setRangeTo(""); setRangeOpen(false); setRangeError("");
  };

  const load = async (reset: boolean, account = selectedAccount, channel = selectedChannel) => {
    const id = ++requestId.current;
    reset ? setLoading(true) : setMore(true);
    if (reset) setError("");
    try {
      const query = new URLSearchParams();
      if (account) query.set("account", account);
      if (channel) query.set("channel", channel);
      addTimeRange(query);
      if (!reset && cursor) query.set("cursor", cursor);
      const data = await getJSON(`/api/cloudinary/camera-images?${query}`, { cache: false });
      if (id !== requestId.current) return;
      setImages((old) => {
        if (reset) return data.images || [];
        const seen = new Set(old.map((image) => image.id));
        return [...old, ...(data.images || []).filter((image: CameraImage) => !seen.has(image.id))];
      });
      setCursor(data.next_cursor || null);
      setTotal(Number(data.total_count) || 0);
      if (data.accounts?.length) setAccounts(data.accounts);
      if (data.channels?.length) setChannels(data.channels);
      setSourceErrors(data.source_errors?.length || 0);
      setLastSync(Date.now());
    } catch (reason: any) {
      if (id === requestId.current) setError(reason?.message || "Không tải được ảnh");
    } finally {
      if (id === requestId.current) { setLoading(false); setMore(false); }
    }
  };

  const refreshLatest = async () => {
    // viewerRef: ảnh mới chèn đầu mảng làm index dịch → ảnh đang xem/zoom bị đổi dưới tay.
    if (busyRef.current || document.hidden || rangeFrom || rangeTo || viewerRef.current) return;
    const id = ++freshRequestId.current;
    setSyncing(true);
    try {
      const query = new URLSearchParams();
      if (selectedAccount) query.set("account", selectedAccount);
      if (selectedChannel) query.set("channel", selectedChannel);
      const data = await getJSON(`/api/cloudinary/camera-images?${query}`, { cache: false });
      if (id !== freshRequestId.current) return;
      setImages((old) => {
        const fresh: CameraImage[] = data.images || [];
        // Trang đầu không đổi → giữ nguyên identity mảng, Preact bail-out khỏi rebuild grid.
        if (fresh.length && old.length >= fresh.length && fresh.every((image, i) => image.id === old[i]?.id))
          return old;
        const freshIds = new Set(fresh.map((image) => image.id));
        return [...fresh, ...old.filter((image) => !freshIds.has(image.id))]
          .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
      });
      setTotal(Number(data.total_count) || 0);
      if (data.accounts?.length) setAccounts(data.accounts);
      if (data.channels?.length) setChannels(data.channels);
      setSourceErrors(data.source_errors?.length || 0);
      setLastSync(Date.now());
    } catch {
      // Đồng bộ nền lỗi không che gallery đang xem; lần poll sau sẽ thử lại.
    } finally {
      if (id === freshRequestId.current) setSyncing(false);
    }
  };

  useEffect(() => {
    if (skipFirstLoad.current) { // hydrate từ cache → hiện ngay, chỉ đồng bộ nền
      skipFirstLoad.current = false;
      refreshLatest();
      return;
    }
    load(true, selectedAccount, selectedChannel);
  }, [selectedAccount, selectedChannel, rangeFrom, rangeTo]);
  useEffect(() => {
    if (rangeFrom || rangeTo) return;
    const timer = window.setInterval(refreshLatest, 10000);
    const onVisible = () => { if (!document.hidden) refreshLatest(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      freshRequestId.current += 1;
    };
  }, [selectedAccount, selectedChannel, rangeFrom, rangeTo]);

  const rangeActive = !!(rangeFrom || rangeTo);
  const rangeCaption = rangeActive ? `${dateTimeLabel(rangeFrom)} → ${dateTimeLabel(rangeTo)}` : "";

  const groups: { key: string; label: string; images: { image: CameraImage; index: number }[] }[] = [];
  images.forEach((image, index) => {
    const key = dayKey(image.created_at);
    let group = groups[groups.length - 1];
    if (!group || group.key !== key) {
      group = { key, label: dayLabel(image.created_at), images: [] };
      groups.push(group);
    }
    group.images.push({ image, index });
  });

  // Ước lượng chiều cao section cho contain-intrinsic-size (content-visibility: auto):
  // gallery ngang = viewport − 20px padding, grid 3 cột (<520px) / 4 cột, gap 3px,
  // ô vuông, header nhóm ≈ 25px. Sau lần paint đầu, từ khoá `auto` nhớ size thật.
  const gridCols = window.innerWidth >= 520 ? 4 : 3;
  const gridCell = (window.innerWidth - 20 - (gridCols - 1) * 3) / gridCols;
  const dayHeight = (count: number) => {
    const rows = Math.ceil(count / gridCols);
    return Math.round(25 + rows * gridCell + (rows - 1) * 3);
  };

  return (
    <div class="camera-gallery">
      <section class="camera-hero">
        <div class="camera-lens" aria-hidden="true"><span /></div>
        <div class="camera-hero-copy">
          <span class="camera-kicker">CLOUD CAMERA</span>
          <b>{loading ? "Đang mở cuộn phim…" : total > images.length ? `${images.length} / ${total} ảnh đã tải` : `${images.length} ảnh`}</b>
          <small>{rangeActive ? rangeCaption : "channel_11 + channel_14 · tự cập nhật 10 giây"}</small>
        </div>
        <span class={rangeActive ? "camera-live history" : syncing ? "camera-live syncing" : "camera-live"}><i />{rangeActive ? "Lịch sử" : syncing ? "Đang đồng bộ" : "Trực tiếp"}</span>
        <button class="camera-refresh" onClick={() => rangeActive ? load(true) : refreshLatest()} disabled={loading || syncing} title="Làm mới"><Icon name="refresh" size={19} /></button>
      </section>

      {accounts.length > 1 && (
        <div class="camera-sources" aria-label="Lọc theo nguồn Cloudinary">
          <button class={!selectedAccount ? "active" : ""} onClick={() => setSelectedAccount("")}>Tất cả nguồn</button>
          {accounts.map((account) => <button class={selectedAccount === account.id ? "active" : ""} onClick={() => setSelectedAccount(account.id)} key={account.id}>{account.label}</button>)}
        </div>
      )}
      <div class="camera-channels" aria-label="Lọc theo kênh camera">
        <button class={!selectedChannel ? "active" : ""} onClick={() => setSelectedChannel("")}>Tất cả camera</button>
        {channels.map((channel) => <button class={selectedChannel === channel.id ? "active" : ""} onClick={() => setSelectedChannel(channel.id)} key={channel.id}>{channel.label}</button>)}
        <button class={rangeActive ? "camera-time-btn active" : "camera-time-btn"} onClick={openRange}><Icon name="clock" size={14} /> Thời gian</button>
      </div>
      {rangeActive && <button class="camera-range-active" onClick={clearRange}><Icon name="clock" size={14} /><span>{rangeCaption}</span><Icon name="close" size={14} /></button>}
      {sourceErrors > 0 && <p class="camera-source-warn">Có {sourceErrors} nguồn tạm thời chưa kết nối được.</p>}

      {loading ? <Loading label="Đang lấy ảnh từ Cloudinary…" /> : error ? <ErrorState msg={error} onRetry={() => load(true)} /> : images.length === 0 ? (
        <div class="camera-empty"><Icon name="camera" size={38} /><b>Chưa có ảnh</b><span>{rangeActive ? "Không có ảnh trong khoảng thời gian này." : "Thư mục camera_2026 đang trống."}</span></div>
      ) : groups.map((group) => (
        <section class="camera-day" key={group.key} style={`contain-intrinsic-size: auto ${dayHeight(group.images.length)}px`}>
          <div class="camera-day-head"><b>{group.label}</b><span>{group.images.length} ảnh</span></div>
          <div class="camera-grid">
            {group.images.map(({ image, index }) => (
              <button class="camera-shot-card" key={image.id} onClick={() => setViewer(index)} aria-label={`Xem ${image.name}`}>
                <img src={image.thumbnail_url} alt="" loading={index < 6 ? "eager" : "lazy"}
                  fetchPriority={index < 3 ? "high" : "auto"} decoding="async" />
                <span class="camera-shot-time">{timeLabel(image.created_at)}</span>
                <span class="camera-shot-source">{image.channel.replace("_", " ")}</span>
              </button>
            ))}
          </div>
        </section>
      ))}

      {!loading && cursor && (
        <button class="camera-more" onClick={() => load(false)} disabled={more}>
          {more ? <LoadingInline label="Đang tải thêm…" /> : <>Xem ảnh cũ hơn <Icon name="chevronDown" size={18} /></>}
        </button>
      )}
      {!loading && lastSync > 0 && <p class="camera-sync-note">Đồng bộ gần nhất lúc {timeLabel(new Date(lastSync).toISOString())}</p>}
      {rangeOpen && (
        <div class="modal-overlay" onClick={() => setRangeOpen(false)}>
          <div class="modal-sheet camera-range-sheet" onClick={(event: any) => event.stopPropagation()}>
            <div class="modal-head"><b><Icon name="clock" size={18} /> Đi tới khoảng thời gian</b>
              <button class="camera-viewer-btn" onClick={() => setRangeOpen(false)}><Icon name="close" size={18} /></button>
            </div>
            <p>Chọn thời điểm bắt đầu và kết thúc. Kết quả vẫn được chia theo ngày và camera.</p>
            <label><span>Từ</span><input type="datetime-local" value={draftFrom} onInput={(event: any) => setDraftFrom(event.currentTarget.value)} /></label>
            <label><span>Đến</span><input type="datetime-local" value={draftTo} onInput={(event: any) => setDraftTo(event.currentTarget.value)} /></label>
            {rangeError && <p class="camera-range-error">{rangeError}</p>}
            <div class="camera-range-actions">
              {rangeActive && <button class="btn" onClick={clearRange}>Về mới nhất</button>}
              <button class="btn primary" onClick={applyRange}>Xem khoảng này</button>
            </div>
          </div>
        </div>
      )}
      {viewer !== null && <CameraViewer images={images} start={viewer} onClose={() => setViewer(null)} />}
    </div>
  );
}
