// Trang NỢ QUÁ HẠN (#/no-qua-han, menu ☰ Thêm → Tài chính) — khách ĐÃ NHẬN HÀNG
// nhưng chưa trả tiền quá N ngày, nợ lâu nhất trước. Mỗi dòng đọc đúng câu cảnh
// báo trong thông báo: "Loan Phú đang có công nợ đã 3 ngày chưa thanh toán từ 3
// đơn hàng". Bấm → trang thu tiền của khách đó. Chỉ văn phòng.
// Server nhắc lại MỖI NGÀY (8h VN) qua trung tâm thông báo + push FCM.
// Nối: api.getDebtAlerts, ui/SearchBar, ui/states, realtime.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import { getDebtAlerts, isOffice, type DebtAlert } from "../api";
import { onRealtime } from "../realtime";
import { money, foldVN } from "../format";
import { Loading, ErrorState, EmptyState } from "../ui/states";
import { SearchBar } from "../ui/SearchBar";
import { Icon } from "../ui/Icon";

type Data = { alerts: DebtAlert[]; count: number; total: number; min_days: number };
const THRESHOLDS = [1, 3, 7, 15];
let cache: Record<number, Data | undefined> = {};
onRealtime((e) => {
  if (["order_changed", "orders_changed", "customer_changed", "resync"].includes(e.type)) cache = {};
});

/** "đã 3 ngày chưa thanh toán từ 3 đơn hàng" — cùng câu với thông báo của server. */
function alertLine(a: DebtAlert): string {
  return `đã ${a.days} ngày chưa thanh toán từ ${a.order_count} đơn hàng`;
}

export function DebtAlerts() {
  const office = isOffice();
  const [days, setDays] = useState(1);
  const [data, setData] = useState<Data | null>(cache[1] || null);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const reqSeq = useRef(0);

  const reload = async (soft = false, threshold = days) => {
    // Đổi ngưỡng liên tiếp: chỉ lượt tải MỚI NHẤT được đổ ra màn hình.
    const seq = ++reqSeq.current;
    try {
      if (!soft) setData(cache[threshold] || null);
      const next = await getDebtAlerts(threshold);
      cache[threshold] = next;
      if (seq !== reqSeq.current) return;
      setData(next);
      setErr("");
    } catch (ex: any) {
      if (seq === reqSeq.current) setErr(ex?.message || "Không tải được danh sách nợ quá hạn");
    }
  };
  useEffect(() => { reload(); }, []);
  useEffect(() => {
    const off = onRealtime((e) => {
      if (["order_changed", "orders_changed", "customer_changed", "resync"].includes(e.type)) {
        reload(true, days);
      }
    });
    return off;
  }, [days]);

  // soft = giữ danh sách cũ trong lúc tải ngưỡng mới (không nháy cả trang).
  const pickDays = (d: number) => { setDays(d); reload(true, d); };

  const alerts = data?.alerts || [];
  const normalized = foldVN(query.trim());
  const shown = useMemo(
    () => normalized ? alerts.filter((a) => foldVN(a.name).includes(normalized)) : alerts,
    [alerts, normalized],
  );

  if (!office) {
    return (
      <div>
        <PageHead fallback="#/home" title="Nợ quá hạn" />
        <div class="card muted small">🔒 Chỉ văn phòng mới xem được công nợ.</div>
      </div>
    );
  }
  if (err && !data) return <ErrorState msg={err} onRetry={() => reload()} />;
  if (!data) return <Loading />;

  return (
    <div class="debt-alerts">
      <PageHead fallback="#/home" title="Nợ quá hạn"
        sub={<>{data.count} khách · {money(data.total)}</>} />

      <div class="chips debt-days">
        {THRESHOLDS.map((d) => (
          <button key={d} class={"chip" + (days === d ? " active" : "")} onClick={() => pickDays(d)}>
            từ {d} ngày
          </button>
        ))}
      </div>

      <div class="debt-search"><SearchBar value={query} onInput={setQuery} placeholder="Tìm khách…" /></div>

      {err && <p class="notice err small">⚠️ {err}</p>}

      {shown.length === 0 ? (
        <EmptyState icon="🎉">
          {query ? "Không có khách khớp tìm kiếm" : `Không có khách nào nợ quá ${days} ngày.`}
        </EmptyState>
      ) : (
        <ul class="debt-list">
          {shown.map((a) => (
            <li class={"debt-row" + (a.blocked ? " blocked" : "")} key={a.key}>
              <a class="debt-main" href={`#/order/${a.source_thread_id}/thanh-toan`}>
                <span class={"debt-days-badge" + (a.days >= 7 ? " hot" : "")}>
                  {a.days}<small>ngày</small>
                </span>
                <span class="debt-copy">
                  <b class="debt-name">{a.name}</b>
                  <span class="muted small">{alertLine(a)}</span>
                </span>
                <span class="debt-amt">{money(a.total)}</span>
              </a>
              <div class="debt-actions">
                <a class="btn small ghost" href={`#/khach/${encodeURIComponent(a.key)}`}>
                  <Icon name="user" size={14} /> Khách
                </a>
                <a class="btn small primary" href={`#/order/${a.source_thread_id}/thanh-toan`}>
                  <Icon name="banknote" size={14} /> Thu tiền
                </a>
              </div>
              {a.blocked && (
                <div class="debt-note"><Icon name="lock" size={13} /> Chưa liên kết KiotViet — không thu được</div>
              )}
            </li>
          ))}
        </ul>
      )}

      <p class="muted small debt-foot">
        Đếm từ ngày <b>giao hàng xong</b>; đơn đã ẩn khỏi trang thu tiền và đơn bỏ theo dõi nợ không tính.
        Mỗi sáng hệ thống gửi lại thông báo cho tới khi khách hết nợ.
      </p>
    </div>
  );
}
