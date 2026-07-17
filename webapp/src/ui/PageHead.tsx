// HEADER TRANG CHUẨN dùng chung — nút back (BackLink) + tiêu đề + phụ đề + slot
// phải. Thay cho các header tự chế (.wg-head/.cn-head/.bm-head/h2.page-h…) để
// mọi trang chi tiết/dashboard cùng một khung. CSS: .page-head* trong styles.css
// (alias của .prod-detail-head). Dùng: <PageHead fallback="#/kho" title="…" sub="…" right={<button/>}/>
import { BackLink } from "../nav";

export function PageHead({ fallback, title, sub, right }: {
  fallback: string;
  title: any;
  sub?: any;
  right?: any;
}) {
  return (
    <div class="page-head">
      <BackLink fallback={fallback} />
      <div class="page-head-txt">
        <h2 class="page-head-title">{title}</h2>
        {sub ? <div class="page-head-sub">{sub}</div> : null}
      </div>
      {right}
    </div>
  );
}
