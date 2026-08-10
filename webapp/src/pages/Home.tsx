// Trang chủ (#/home) — mọi mục của app gom theo NHÓM liên quan, mỗi mục 1 ô bấm được.
// Thay menu "Mục khác" dài (bị cắt) bằng trang cuộn được, có phân nhóm. Vào từ nút ☰
// Thêm ở thanh điều hướng. Danh mục mục = homeMenu.ts (dùng chung với recent.ts).
// Đầu trang có khối GẦN ĐÂY: 6 mục vừa mở gần nhất (recent.ts, nhớ theo máy).
import { useEffect, useRef, useState } from "preact/hooks";
import { currentUser } from "../api";
import { foldVN } from "../format";
import { GROUPS, itemAllowed, type MenuItem } from "../homeMenu";
import { recentHrefs } from "../recent";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";
import { EmptyState } from "../ui/states";

const RECENT_SHOW = 6;

export function Home() {
  const role = currentUser()?.role;
  const office = role === "admin" || role === "van_phong";
  const admin = role === "admin";
  const [query, setQuery] = useState("");
  const searchInput = useRef<HTMLInputElement>(null);
  // Desktop (có bàn phím): bấm "/" ở bất kỳ đâu → nhảy vào ô tìm kiếm.
  // Cùng luật màn hình rộng như phím tắt Escape ở dashboard Đơn (OrdersList).
  useEffect(() => {
    const onSlash = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (!window.matchMedia("(min-width: 720px)").matches) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      // Đang gõ trong ô nhập thì "/" là ký tự bình thường, không cướp.
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return;
      e.preventDefault();
      searchInput.current?.focus();
      searchInput.current?.select();
    };
    window.addEventListener("keydown", onSlash);
    return () => window.removeEventListener("keydown", onSlash);
  }, []);
  // Mục GẦN ĐÂY: đọc 1 lần lúc mở trang (mở lại trang là đọc lại) — không cần theo
  // dõi liên tục vì đang ở đây thì không sinh lượt mới. Lọc theo quyền rồi cắt 6 ô.
  const recent: MenuItem[] = (() => {
    const byHref = new Map(GROUPS.flatMap((g) => g.items).map((it) => [it.href, it]));
    const out: MenuItem[] = [];
    for (const href of recentHrefs()) {
      const it = byHref.get(href);
      if (it && itemAllowed(it, office, admin)) out.push(it);
      if (out.length >= RECENT_SHOW) break;
    }
    return out;
  })();

  const normalizedQuery = foldVN(query.trim());
  const visibleGroups = GROUPS.map((g) => {
    const allowedItems = g.items.filter((it) => itemAllowed(it, office, admin));
    const items = normalizedQuery
      ? allowedItems.filter((it) => foldVN(`${it.label} ${g.title}`).includes(normalizedQuery))
      : allowedItems;
    return { ...g, items };
  }).filter((g) => g.items.length > 0);

  return (
    <div class="home">
      <div class="home-search">
        <SearchBar value={query} onInput={setQuery} placeholder="Tìm trong menu Thêm…" inputRef={searchInput} />
      </div>
      {/* Gần đây — ẩn khi đang tìm kiếm (lúc đó người ta muốn thấy kết quả, không phải lối tắt) */}
      {!normalizedQuery && recent.length > 0 && (
        <section class="home-grp home-recent">
          <div class="home-grp-h"><Icon name="history" size={15} /> Gần đây</div>
          <div class="home-grid">
            {recent.map((it) => (
              <a class="home-tile" href={it.href} key={"r-" + it.href}>
                <span class="home-tile-ic"><Icon name={it.icon} size={22} /></span>
                <span class="home-tile-lb">{it.label}</span>
              </a>
            ))}
          </div>
        </section>
      )}
      {visibleGroups.map((g) => {
        return (
          <section class="home-grp" key={g.title}>
            <div class="home-grp-h"><Icon name={g.icon} size={15} /> {g.title}</div>
            <div class="home-grid">
              {g.items.map((it) => (
                <a class="home-tile" href={it.href} key={it.href}>
                  <span class="home-tile-ic"><Icon name={it.icon} size={22} /></span>
                  <span class="home-tile-lb">{it.label}</span>
                </a>
              ))}
            </div>
          </section>
        );
      })}
      {!visibleGroups.length && (
        <EmptyState icon="🔍">
          Không tìm thấy mục phù hợp{" "}
          <button class="btn small" onClick={() => setQuery("")}>Xoá tìm kiếm</button>
        </EmptyState>
      )}
    </div>
  );
}
