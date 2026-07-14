// HƯỚNG DẪN SỬ DỤNG (#/huong-dan) — danh sách bài + bài chi tiết (#/huong-dan/:key).
// Nút "?" nổi truyền ?from=<trang đang xem> → danh sách đẩy bài LIÊN QUAN trang đó lên
// đầu ("📍 Trang bạn đang xem"), phần còn lại nhóm theo mục. Nội dung tĩnh (HTML do ta
// viết) từ guides/registry.ts. Nối: ui/Icon, nav.BackLink, guides/*.
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { currentUser, isOffice } from "../api";
import type { Guide } from "../guides/types";
import { GUIDE_CATS, guidesForRoute, normalizeFrom, visibleGuides } from "../guides/types";
import { GUIDES, guideByKey } from "../guides/registry";

// Quyền người xem hiện tại — quyết định bài nào hiện.
function viewerPerm() {
  return { office: isOffice(), admin: currentUser()?.role === "admin" };
}

function AiGuideNote() {
  return (
    <div class="guide-ai-note">
      <Icon name="info" size={14} />
      <span>Toàn bộ hướng dẫn trong mục này được viết bởi AI, nên có thể cần Duy kiểm tra lại khi có điểm chưa rõ.</span>
    </div>
  );
}

// Nhãn quyền RÕ RÀNG trên bài chỉ-văn-phòng / chỉ-admin.
function PermBadge({ g }: { g: Guide }) {
  if (g.admin) return <span class="guide-perm admin"><Icon name="lock" size={11} /> Chỉ admin</span>;
  if (g.office) return <span class="guide-perm"><Icon name="lock" size={11} /> Chỉ văn phòng</span>;
  return null;
}

function GuideCard({ g }: { g: Guide }) {
  return (
    <a class="cash-box" href={`#/huong-dan/${g.key}`}>
      <div class="cash-box-name"><Icon name={g.icon} size={16} /> {g.title} <PermBadge g={g} /></div>
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
  // CHỈ hiện bài người xem có quyền — bài chỉ-văn-phòng/admin bị ẩn với staff (cả ở
  // khối "Trang bạn đang xem" lẫn danh sách theo mục).
  const guides = visibleGuides(GUIDES, viewerPerm());
  const related = from ? guidesForRoute(guides, from) : [];
  const relatedKeys = new Set(related.map((g) => g.key));
  const rest = guides.filter((g) => !relatedKeys.has(g.key));

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
  const perm = viewerPerm();
  // Staff mở trực tiếp URL bài chỉ-văn-phòng/admin (vd qua link cũ) → chặn, không lộ nội dung.
  const denied = !!g && ((g.office && !perm.office) || (g.admin && !perm.admin));

  if (!g || denied) {
    return (
      <div class="guide">
        <div class="prod-detail-head">
          <BackLink fallback="#/huong-dan" />
          <div><div class="prod-sp big">{denied ? "Bài này chỉ dành cho văn phòng" : "Không tìm thấy bài hướng dẫn"}</div></div>
        </div>
        {denied && <div class="guide-ai-note"><Icon name="lock" size={14} /><span>Tính năng trong bài này chỉ văn phòng/admin dùng được, nên hướng dẫn cũng chỉ hiện cho văn phòng.</span></div>}
        <a class="cash-box" href="#/huong-dan">← Về danh sách hướng dẫn</a>
      </div>
    );
  }

  return (
    <div class="guide">
      <div class="prod-detail-head">
        <BackLink fallback="#/huong-dan" />
        <div>
          <div class="prod-sp big"><Icon name={g.icon} size={17} /> Hướng dẫn: {g.title} <PermBadge g={g} /></div>
          <div class="prod-date muted">{g.desc}</div>
        </div>
      </div>
      {(g.office || g.admin) && (
        <div class="guide-office-note">
          <Icon name="lock" size={14} />
          <span>{g.admin ? "Trang này chỉ ADMIN dùng được." : "Trang này chỉ VĂN PHÒNG dùng được."} Nhân viên sẽ không thấy bài này.</span>
        </div>
      )}
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
