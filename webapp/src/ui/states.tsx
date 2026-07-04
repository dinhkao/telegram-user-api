// Trạng thái màn hình DÙNG CHUNG — loading / empty / error. Trước đây mỗi màn tự
// viết (.error vs .error-banner, "muted center" vs "muted", 5 câu trống khác nhau).
// Dùng: <Loading/> khi đang tải, <EmptyState> khi rỗng, <ErrorState onRetry> khi lỗi.

export function Loading({ label = "Đang tải…" }: { label?: string }) {
  return <p class="state-loading muted center">{label}</p>;
}

export function EmptyState({ children, icon }: { children: any; icon?: string }) {
  return (
    <p class="state-empty muted center">
      {icon ? <span class="state-empty-ic">{icon}</span> : null}
      {children}
    </p>
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
