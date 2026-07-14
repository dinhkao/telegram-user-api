// HƯỚNG DẪN SỬ DỤNG (#/huong-dan) — danh sách bài + bài chi tiết (#/huong-dan/:key).
// Nút "?" nổi truyền ?from=<trang đang xem> → danh sách đẩy bài LIÊN QUAN trang đó lên
// đầu ("📍 Trang bạn đang xem"), phần còn lại nhóm theo mục. Nội dung tĩnh (HTML do ta
// viết) từ guides/registry.ts. Nối: ui/Icon, nav.BackLink, guides/*.
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import type { Guide } from "../guides/types";
import { GUIDE_CATS, guidesForRoute, normalizeFrom } from "../guides/types";
import { GUIDES, guideByKey } from "../guides/registry";

function AiGuideNote() {
  return (
    <div class="guide-ai-note">
      <Icon name="info" size={14} />
      <span>Toàn bộ hướng dẫn trong mục này được viết bởi AI, nên có thể cần Duy kiểm tra lại khi có điểm chưa rõ.</span>
    </div>
  );
}

function GuideCard({ g }: { g: Guide }) {
  return (
    <a class="cash-box" href={`#/huong-dan/${g.key}`}>
      <div class="cash-box-name"><Icon name={g.icon} size={16} /> {g.title}</div>
      <div class="muted small">{g.desc}</div>
    </a>
  );
}

// Đọc ?from= trong hash (vd "#/huong-dan?from=%23%2Fket").
function readFrom(hash: string): string {
  const q = hash.indexOf("?");
  if (q < 0) return "";
  const params = new URLSearchParams(hash.slice(q + 1));
  return params.get("from") || "";
}

export function GuidesList({ hash }: { hash: string }) {
  const from = readFrom(hash);
  const related = from ? guidesForRoute(GUIDES, from) : [];
  const relatedKeys = new Set(related.map((g) => g.key));
  const rest = GUIDES.filter((g) => !relatedKeys.has(g.key));

  return (
    <div class="guide-list">
      <div class="muted small guide-intro">
        Chọn 1 bài để xem cách dùng. Có thắc mắc gì cứ hỏi Duy.
      </div>
      <AiGuideNote />

      {related.length > 0 && (
        <section class="guide-related">
          <div class="guide-related-hd">
            <Icon name="info" size={14} /> Trang bạn đang xem
          </div>
          {related.map((g) => <GuideCard key={g.key} g={g} />)}
        </section>
      )}

      {GUIDE_CATS.map((cat) => {
        const items = rest.filter((g) => g.cat === cat);
        if (!items.length) return null;
        return (
          <section class="guide-cat" key={cat}>
            <div class="guide-cat-hd">{cat}</div>
            {items.map((g) => <GuideCard key={g.key} g={g} />)}
          </section>
        );
      })}
    </div>
  );
}

// Trang chi tiết 1 bài — generic, tra theo key trong hash (#/huong-dan/<key>).
export function GuideDetail({ hash }: { hash: string }) {
  const path = hash.split("?")[0];
  const key = path.replace(/^#\/huong-dan\//, "").replace(/\/$/, "");
  const g = guideByKey(key);

  if (!g) {
    return (
      <div class="guide">
        <div class="prod-detail-head">
          <BackLink fallback="#/huong-dan" />
          <div><div class="prod-sp big">Không tìm thấy bài hướng dẫn</div></div>
        </div>
        <a class="cash-box" href="#/huong-dan">← Về danh sách hướng dẫn</a>
      </div>
    );
  }

  return (
    <div class="guide">
      <div class="prod-detail-head">
        <BackLink fallback="#/huong-dan" />
        <div>
          <div class="prod-sp big"><Icon name={g.icon} size={17} /> Hướng dẫn: {g.title}</div>
          <div class="prod-date muted">{g.desc}</div>
        </div>
      </div>
      <AiGuideNote />
      {g.sections.map((s, i) => (
        <section class="card guide-sect" key={i}>
          <h3><span class="guide-num">{i + 1}</span> {s.title}</h3>
          <div dangerouslySetInnerHTML={{ __html: s.html }} />
        </section>
      ))}
    </div>
  );
}

// Giữ export cũ để main.tsx cũ không vỡ nếu còn tham chiếu (đã chuyển sang GuideDetail).
export { normalizeFrom };
