import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { Icon } from "../ui/Icon";
import { ErrorState, Loading, LoadingInline } from "../ui/states";
import { usePopupBack } from "../ui/usePopupBack";

type CameraAccount = { id: string; label: string; folder: string };
type CameraImage = {
  id: string;
  account_id: string;
  account_label: string;
  name: string;
  created_at?: string;
  width: number;
  height: number;
  bytes: number;
  thumbnail_url: string;
  preview_url: string;
  original_url: string;
};

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
  return new Intl.DateTimeFormat("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
};
const timeLabel = (value?: string) => value
  ? new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value))
  : "";

function CameraViewer({ images, start, onClose }: { images: CameraImage[]; start: number; onClose: () => void }) {
  const [index, setIndex] = useState(start);
  usePopupBack(true, onClose);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1));
      if (event.key === "ArrowRight") setIndex((value) => Math.min(images.length - 1, value + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [images.length]);
  const image = images[index];
  if (!image) return null;
  return (
    <div class="camera-viewer" role="dialog" aria-modal="true" aria-label={`Ảnh ${image.name}`}>
      <div class="camera-viewer-top">
        <span class="camera-viewer-source">{image.account_label}</span>
        <a class="camera-viewer-btn" href={image.original_url} target="_blank" rel="noopener" title="Mở ảnh gốc"><Icon name="download" size={20} /></a>
        <button class="camera-viewer-btn" onClick={onClose} title="Đóng"><Icon name="close" size={22} /></button>
      </div>
      <img class="camera-viewer-img" src={image.preview_url} alt={image.name} />
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
  const [images, setImages] = useState<CameraImage[]>([]);
  const [accounts, setAccounts] = useState<CameraAccount[]>([]);
  const [selected, setSelected] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  const [sourceErrors, setSourceErrors] = useState(0);
  const [viewer, setViewer] = useState<number | null>(null);
  const requestId = useRef(0);

  const load = async (reset: boolean, account = selected) => {
    const id = ++requestId.current;
    reset ? setLoading(true) : setMore(true);
    if (reset) setError("");
    try {
      const query = new URLSearchParams();
      if (account) query.set("account", account);
      if (!reset && cursor) query.set("cursor", cursor);
      const data = await getJSON(`/api/cloudinary/camera-images?${query}`, { cache: false });
      if (id !== requestId.current) return;
      setImages((old) => reset ? data.images || [] : [...old, ...(data.images || [])]);
      setCursor(data.next_cursor || null);
      if (data.accounts?.length) setAccounts(data.accounts);
      setSourceErrors(data.source_errors?.length || 0);
    } catch (reason: any) {
      if (id === requestId.current) setError(reason?.message || "Không tải được ảnh");
    } finally {
      if (id === requestId.current) { setLoading(false); setMore(false); }
    }
  };

  useEffect(() => { load(true, selected); }, [selected]);

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

  return (
    <div class="camera-gallery">
      <section class="camera-hero">
        <div class="camera-lens" aria-hidden="true"><span /></div>
        <div class="camera-hero-copy">
          <span class="camera-kicker">CLOUD CAMERA</span>
          <b>{loading ? "Đang mở cuộn phim…" : `${images.length} ảnh đã tải`}</b>
          <small>Thư mục camera_2026 · mới nhất trước</small>
        </div>
        <button class="camera-refresh" onClick={() => load(true)} disabled={loading} title="Làm mới"><Icon name="refresh" size={19} /></button>
      </section>

      {accounts.length > 1 && (
        <div class="camera-sources" aria-label="Lọc theo nguồn Cloudinary">
          <button class={!selected ? "active" : ""} onClick={() => setSelected("")}>Tất cả</button>
          {accounts.map((account) => <button class={selected === account.id ? "active" : ""} onClick={() => setSelected(account.id)} key={account.id}>{account.label}</button>)}
        </div>
      )}
      {sourceErrors > 0 && <p class="camera-source-warn">Có {sourceErrors} nguồn tạm thời chưa kết nối được.</p>}

      {loading ? <Loading label="Đang lấy ảnh từ Cloudinary…" /> : error ? <ErrorState msg={error} onRetry={() => load(true)} /> : images.length === 0 ? (
        <div class="camera-empty"><Icon name="camera" size={38} /><b>Chưa có ảnh</b><span>Thư mục camera_2026 đang trống.</span></div>
      ) : groups.map((group) => (
        <section class="camera-day" key={group.key}>
          <div class="camera-day-head"><b>{group.label}</b><span>{group.images.length} ảnh</span></div>
          <div class="camera-grid">
            {group.images.map(({ image, index }) => (
              <button class="camera-shot-card" key={image.id} onClick={() => setViewer(index)} aria-label={`Xem ${image.name}`}>
                <img src={image.thumbnail_url} alt="" loading="lazy" decoding="async" />
                <span class="camera-shot-time">{timeLabel(image.created_at)}</span>
                {accounts.length > 1 && <span class="camera-shot-source">{image.account_label}</span>}
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
      {viewer !== null && <CameraViewer images={images} start={viewer} onClose={() => setViewer(null)} />}
    </div>
  );
}
