// Trạng thái màn hình DÙNG CHUNG — loading / empty / error. Trước đây mỗi màn tự
// viết (.error vs .error-banner, "muted center" vs "muted", 5 câu trống khác nhau).
// Dùng: <Loading/> khi đang tải, <EmptyState> khi rỗng, <ErrorState onRetry> khi lỗi.

/** Vòng xoay tải — SVG cung tròn quay + co giãn (kiểu Material). Dùng lẻ được
 *  (nút đang bận, khối nhỏ): <Spinner size={16}/>. */
export function Spinner({ size = 24 }: { size?: number }) {
  return (
    <svg class="spin" width={size} height={size} viewBox="0 0 24 24" role="status" aria-label="Đang tải">
      <circle class="spin-track" cx="12" cy="12" r="9" fill="none" stroke-width="2.5" />
      <circle class="spin-arc" cx="12" cy="12" r="9" fill="none" stroke-width="2.5" stroke-linecap="round" />
    </svg>
  );
}

/** Bản NHỎ nằm trong dòng — cho khối con/sentinel tải-thêm/nút bận. Kế thừa
 *  cỡ chữ + màu từ cha (đặt trong <p class="muted small"> như cũ). */
export function LoadingInline({ label = "Đang tải…" }: { label?: string }) {
  return (
    <span class="loading-inline">
      <Spinner size={14} />
      {label}
    </span>
  );
}

export function Loading({ label = "Đang tải…" }: { label?: string }) {
  return (
    <div class="state-loading muted center" role="status">
      <Spinner />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ children, icon }: { children: any; icon?: string }) {
  return (
    <p class="state-empty muted center">
      {icon ? <span class="state-empty-ic">{icon}</span> : null}
      {children}
    </p>
  );
}

/** Khung xương (skeleton) nhấp nháy khi tải danh sách — thay chữ "Đang tải…".
 *  rows = số card giả. Dùng: {!data ? <SkeletonList/> : …}. */
export function SkeletonList({ rows = 5 }: { rows?: number }) {
  return (
    <div class="skel-list" aria-busy="true" aria-label="Đang tải">
      {Array.from({ length: rows }).map((_, i) => (
        <div class="skel-card" key={i}>
          <div class="skel-line w60" />
          <div class="skel-line w40" />
          <div class="skel-line w80" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ msg, onRetry }: { msg?: string; onRetry?: () => void }) {
  return (
    <div class="state-error">
      <p class="error">{msg || "Có lỗi xảy ra. Kiểm tra mạng rồi thử lại."}</p>
      {onRetry ? <button class="btn small" onClick={onRetry}>Thử lại</button> : null}
    </div>
  );
}
