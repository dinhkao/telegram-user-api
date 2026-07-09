// Lớp gọi API — gắn token, base URL cấu hình được (WebView trỏ Tailscale IP),
// cache GET (network-first, rớt mạng đọc cache) + hàng đợi POST offline (offline.ts).
import { flushQueue, queuePost, readCache, writeCache } from "./offline";

// Trạng thái MẠNG THẬT: dựa trên fetch tới server có tới được hay không, KHÔNG dựa
// navigator.onLine (Android WebView qua Tailscale báo sai → banner "mất mạng" ảo).
// getJSON/postJSON gọi setNet() theo kết quả thực. Mặc định online → không báo sai lúc mở.
let _netOk = true;
const _netSubs = new Set<(ok: boolean) => void>();
export function netOk(): boolean { return _netOk; }
export function onNetStatus(fn: (ok: boolean) => void): () => void { _netSubs.add(fn); return () => { _netSubs.delete(fn); }; }
function setNet(ok: boolean): void {
  if (ok === _netOk) return;
  _netOk = ok;
  _netSubs.forEach((f) => { try { f(ok); } catch { /* ignore */ } });
}

export function serverUrl(): string {
  // APK giờ nạp webapp từ URL server (qua Tailscale) nên webapp luôn cùng origin
  // với API → dùng đường dẫn tương đối. Xoá giá trị cũ (nếu có) để không ghim IP cũ.
  if (localStorage.getItem("server_url")) localStorage.removeItem("server_url");
  return "";
}

export function getToken(): string {
  return localStorage.getItem("token") || "";
}

export function setAuth(token: string, user: { username: string; display_name: string; role: string } | null) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
  if (user) localStorage.setItem("user", JSON.stringify(user));
  else localStorage.removeItem("user");
}

export function currentUser(): { username: string; display_name: string; role: string } | null {
  try {
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch {
    return null;
  }
}

/** Văn phòng = role admin hoặc van_phong. Chỉ văn phòng được: nhận tiền + tạo thanh toán. */
export function isOffice(): boolean {
  const r = currentUser()?.role;
  return r === "admin" || r === "van_phong";
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parse(res: Response): Promise<any> {
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    window.location.hash = "#/login";
    throw new ApiError(401, data.error || "Cần đăng nhập");
  }
  if (!res.ok) throw new ApiError(res.status, data.error || `Lỗi ${res.status}`);
  return data;
}

/** GET network-first; mất mạng → trả cache (kèm cờ _stale) nếu có.
 *  cache=false cho kết quả search theo phím gõ — không rác localStorage. */
export async function getJSON(path: string, opts?: { cache?: boolean }): Promise<any> {
  const url = serverUrl() + path;
  const useCache = opts?.cache !== false;
  try {
    const res = await fetch(url, { headers: headers() });
    setNet(true);   // server phản hồi (kể cả lỗi HTTP) = có mạng
    const data = await parse(res);
    if (useCache) writeCache(path, data);
    return data;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    setNet(false);  // fetch bị reject = mất mạng thật
    const cached = useCache ? readCache(path) : null;
    if (cached) return { ...cached.data, _stale: true, _cachedAt: cached.t };
    throw new Error("Mất mạng và chưa có dữ liệu lưu sẵn");
  }
}

/** POST; queueable=true → mất mạng thì xếp hàng đợi, có mạng gửi lại. */
export async function postJSON(path: string, body: any, opts?: { queueable?: boolean }): Promise<any> {
  const url = serverUrl() + path;
  try {
    const res = await fetch(url, { method: "POST", headers: headers(), body: JSON.stringify(body) });
    setNet(true);
    return await parse(res);
  } catch (e) {
    if (e instanceof ApiError) throw e;
    setNet(false);
    if (opts?.queueable) {
      queuePost(path, body);
      return { ok: true, _queued: true };
    }
    throw new Error("Mất mạng — thao tác này cần mạng, thử lại sau");
  }
}

/** Gửi lại hàng đợi offline (gọi khi online lại / mở app).
 *  401 → GIỮ item (token hết hạn, đăng nhập lại sẽ gửi tiếp — không mất dữ liệu);
 *  4xx khác → BỎ (đơn không còn / dữ liệu sai, retry mãi vô ích); lỗi mạng/5xx → giữ. */
export function replayQueue(): Promise<number> {
  return flushQueue(async (path, body) => {
    const res = await fetch(serverUrl() + path, { method: "POST", headers: headers(), body: JSON.stringify(body) });
    if (res.ok) return "ok";
    if (res.status === 401) return "keep";
    if (res.status >= 400 && res.status < 500) return "drop";
    return "keep";
  });
}

export async function login(username: string, pin: string): Promise<any> {
  const res = await fetch(serverUrl() + "/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, pin }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Đăng nhập thất bại");
  setAuth(data.token, data.user);
  return data.user;
}

// ── Helpers cho trình nhập hoá đơn nâng cao ──────────────────────────────

/** Autocomplete mã/tên SP. Không cache (kết quả theo phím gõ). */
export async function searchProducts(q: string): Promise<{ code: string; name: string }[]> {
  const d = await getJSON(`/api/products?search=${encodeURIComponent(q)}&limit=15`, { cache: false });
  return d.products || [];
}

export type OrderPreview = {
  customer: {
    id: string; name: string | null; score: number; manual?: boolean;
    debt?: number | null; debt_updated_at?: string | null; price_list_name?: string | null;
  } | null;
  candidates: { id: string; name: string; score: number }[];
  invoice: { sp: string; sl: number; price: number; sub: number; list_price?: number }[];
  total: number;
};

export type CustomerPriceList = { name: string | null; items: { sp: string; price: number }[] };

/** Toàn bộ bảng giá hiệu lực của khách (cho popup xem giá). */
export async function getCustomerPriceList(key: string): Promise<CustomerPriceList> {
  const d = await getJSON(`/api/customer/${key}/price-list`, { cache: false });
  return { name: d.name ?? null, items: d.items || [] };
}

// ── Cập nhật APK (manifest do builder deploy vào /app/update) ──
export type ApkVersion = { versionCode: number; versionName?: string; url?: string };
/** Đọc phiên bản APK mới nhất trên máy chủ (versionCode 0 = chưa deploy). */
export async function getApkVersion(): Promise<ApkVersion> {
  const res = await fetch("/app/update/version.json", { cache: "no-store" });
  if (!res.ok) throw new Error("Không đọc được thông tin cập nhật");
  return res.json();
}

// ── Bảng giá chung (kv_store['bang_gia_moi']) ──
export type PriceListSummary = { id: string; name: string; product_count: number };
export type PriceItem = { sp: string; price: number };
export type PriceListFull = { id: string; name: string; items: PriceItem[]; customers: { key: string; name: string }[] };
export type PriceHistoryRow = { sp: string; old_price: number | null; new_price: number | null; changed_by: string; changed_at: number };

export async function getPriceLists(): Promise<PriceListSummary[]> {
  const d = await getJSON("/api/price-lists", { cache: false });
  return d.lists || [];
}
export async function getPriceList(id: string): Promise<PriceListFull> {
  const d = await getJSON(`/api/price-lists/${encodeURIComponent(id)}`, { cache: false });
  return d.list;
}
/** Ghi lại toàn bộ giá (backend diff → lịch sử mỗi SP đổi). */
export async function savePriceList(id: string, items: PriceItem[], name?: string): Promise<PriceListFull> {
  const d = await postJSON(`/api/price-lists/${encodeURIComponent(id)}`, { items, name });
  return d.list;
}
/** Đổi giá 1 SP (view-only + sửa từng dòng) → backend ghi lịch sử. Trả bảng đã cập nhật. */
export async function savePriceOne(id: string, sp: string, price: number): Promise<PriceListFull> {
  const d = await postJSON(`/api/price-lists/${encodeURIComponent(id)}/price`, { sp, price });
  return d.list;
}
export async function getPriceHistory(id: string, sp?: string): Promise<PriceHistoryRow[]> {
  const q = sp ? `?sp=${encodeURIComponent(sp)}` : "";
  const d = await getJSON(`/api/price-lists/${encodeURIComponent(id)}/history${q}`, { cache: false });
  return d.history || [];
}

export type CustomerDetail = {
  key: string; name: string; kh_id?: string | number | null;
  debt?: number | null; debt_updated_at?: any; thread_id?: number | null;
  last_order_at?: any; price_list?: string | number | null;
  personal_price_list?: Record<string, number> | null;
  detectPatterns?: string[];
  default_tasks?: string[];   // việc mặc định — auto-thêm vào đơn khi gán khách
  note?: string;   // ghi chú khách (vd dặn giao hàng) — sửa được từ web
};

/** 1 mục trong feed đơn+thanh toán của khách (xen kẽ theo thời gian giảm dần).
 *  debt_after = nợ SAU sự kiện; debt_est=true → số TÍNH LẠI (nội suy neo mốc KV
 *  thật — bản ghi cũ không lưu số; UI hiện ≈), false → số KiotViet gốc đã lưu. */
export type CustFeedItem =
  | { kind: "order"; ts: number; order: any; debt_after?: number | null; debt_est?: boolean }
  | { kind: "payment"; ts: number; thread_id: number; amount: number; method: string; code?: string; by?: string; at?: string; old_debt?: number | null; new_debt?: number | null; debt_after?: number | null; debt_est?: boolean }
  | { kind: "return"; ts: number; id: number; total: number; note?: string; items: { sp: string; sl: number; price: number }[]; code?: string; by?: string; at?: string; thread_id?: number | null; debt_after?: number | null; debt_est?: boolean };

/** Tạo phiếu TRẢ HÀNG (văn phòng) — HĐ KiotViet giá âm, giảm nợ khách. */
export async function createReturn(key: string, items: { sp: string; sl: number; price: number }[], note = ""): Promise<any> {
  return postJSON(`/api/customers/${encodeURIComponent(key)}/returns`, { items, note });
}
export type ReturnSlip = {
  id: number; customer_key: string; customer_name?: string | null;
  thread_id?: number | null; kv_invoice_id?: number | null; kv_invoice_code?: string | null;
  items: { sp: string; sl: number; price: number }[]; total: number; note?: string;
  debt_before?: number | null; debt_after?: number | null;
  created_by?: string; created_at?: string;
};
/** Dashboard trả hàng — mọi khách, 20/trang. */
export async function listAllReturns(page = 1): Promise<{ returns: ReturnSlip[]; page: number; total_pages: number; total: number }> {
  const d = await getJSON(`/api/returns?page=${page}`, { cache: false });
  return { returns: d.returns || [], page: d.page || page, total_pages: d.total_pages || 1, total: d.total || 0 };
}
export async function getReturn(id: string | number): Promise<ReturnSlip> {
  const d = await getJSON(`/api/returns/${id}`, { cache: false });
  return d.return;
}
/** Sửa phiếu trả NHÁP (văn phòng) — items/ghi chú, khoá khi đã có HĐ KV. */
export async function updateReturn(id: number, items: { sp: string; sl: number; price: number }[], note = ""): Promise<any> {
  return postJSON(`/api/returns/${id}/update`, { items, note });
}
/** Tạo HĐ KiotViet giá âm cho phiếu nháp (văn phòng) — TRỪ công nợ khách. */
export async function invoiceReturn(id: number): Promise<any> {
  return postJSON(`/api/returns/${id}/invoice`, {});
}
/** Xoá HĐ KiotViet của phiếu trả (admin) — hoàn nợ, phiếu về nháp. */
export async function deleteReturnInvoice(id: number): Promise<any> {
  return postJSON(`/api/returns/${id}/delete-invoice`, {});
}
/** Xoá phiếu trả (admin) — CHỈ khi đã xoá HĐ KV (phiếu nháp). */
export async function deleteReturn(id: number): Promise<any> {
  return postJSON(`/api/returns/${id}/delete`, {});
}

/** Feed đơn + thanh toán của 1 khách, gộp 1 dòng thời gian (trang chi tiết khách). */
export async function getCustomerFeed(key: string, page = 1): Promise<{ items: CustFeedItem[]; page: number; total_pages: number; total: number }> {
  const d = await getJSON(`/api/customers/${encodeURIComponent(key)}/feed?page=${page}`, { cache: false });
  return { items: d.items || [], page: d.page || page, total_pages: d.total_pages || 1, total: d.total || 0 };
}

/** Lịch tháng: số biến động theo ngày của khách [{d:'YYYY-MM-DD', o: đơn, p: phiếu thu}]. */
export async function getCustomerFeedDays(key: string): Promise<{ d: string; o: number; p: number }[]> {
  const r = await getJSON(`/api/customers/${encodeURIComponent(key)}/feed?days=1`, { cache: false });
  return r.days || [];
}

/** Mọi biến động của 1 ngày (popup lịch) — giảm dần thời gian. */
export async function getCustomerFeedDay(key: string, day: string): Promise<CustFeedItem[]> {
  const r = await getJSON(`/api/customers/${encodeURIComponent(key)}/feed?day=${encodeURIComponent(day)}`, { cache: false });
  return r.items || [];
}

/** Chi tiết 1 khách (bảng giá riêng + pattern nhận diện). */
export async function getCustomer(key: string): Promise<CustomerDetail> {
  const d = await getJSON(`/api/customers/${encodeURIComponent(key)}`, { cache: false });
  return d.customer;
}

/** Sửa khách: bảng giá riêng, detectPatterns[], default_tasks[] và/hoặc note (ghi chú). */
export async function updateCustomer(
  key: string,
  patch: { personal_price_list?: Record<string, number>; detectPatterns?: string[]; price_list?: string | null; default_tasks?: string[]; note?: string },
): Promise<CustomerDetail> {
  const d = await postJSON(`/api/customers/${encodeURIComponent(key)}`, patch);
  return d.customer;
}

/** Đơn của 1 khách (lọc theo khach_hang_id) — row compact như dashboard, phân trang. */
/** Tạo khách mới (KiotViet + topic + lưu). Trả customer {key,name,kh_id,...}. */
export async function createCustomer(input: { name: string; contactNumber?: string; address?: string }): Promise<any> {
  const d = await postJSON("/api/customers/new", input);
  return d.customer;
}
export async function getCustomerOrders(key: string, page = 1): Promise<{ orders: any[]; page: number; total_pages: number; total: number }> {
  return getJSON(`/api/customers/${encodeURIComponent(key)}/orders?page=${page}`, { cache: false });
}

/** Xem trước kết quả parse text đơn (khách + SP + tổng) — không tạo/lưu.
 *  customerKey: chọn khách tay (đè lên tự nhận diện). */
export async function previewOrder(text: string, customerKey?: string): Promise<OrderPreview> {
  return postJSON("/api/order/preview", { text, customer_key: customerKey || null });
}

/** Kéo nợ MỚI của khách từ KiotViet (cập nhật snapshot) → trả nợ mới. */
export async function refreshCustomerDebt(key: string): Promise<{ debt: number | null }> {
  const d = await postJSON(`/api/customers/${key}/refresh-debt`, {});
  return { debt: d.customer?.debt ?? null };
}

/** Tìm khách TRÊN KiotViet (liên kết kh_id) — trang chi tiết khách. */
export type KvCustomer = { id: number; code: string; name: string; debt: number | null; phone?: string | null };
export async function searchKiotvietCustomers(q: string): Promise<KvCustomer[]> {
  const d = await getJSON(`/api/customers/kiotviet?q=${encodeURIComponent(q)}`, { cache: false });
  return d.customers || [];
}
/** Gắn khách local ↔ khách KiotViet (admin) — kéo nợ ngay. */
export async function linkCustomerKiotviet(key: string, kvId: number): Promise<CustomerDetail> {
  const d = await postJSON(`/api/customers/${encodeURIComponent(key)}/link-kiotviet`, { kv_id: kvId }, { queueable: false });
  return d.customer;
}
export async function unlinkCustomerKiotviet(key: string): Promise<CustomerDetail> {
  const d = await postJSON(`/api/customers/${encodeURIComponent(key)}/unlink-kiotviet`, {}, { queueable: false });
  return d.customer;
}
/** Xoá mềm khách (admin) — server chặn nếu còn liên kết KiotViet. */
export async function deleteCustomer(key: string): Promise<void> {
  await delJSON(`/api/customers/${encodeURIComponent(key)}`);
}

export type PriceInfo = { price: number; source: "personal" | "shared" | null; list_name: string | null };

/** Giá SP theo khách + bảng giá nào (price 0 nếu không có). */
export async function fetchCustomerPrice(customerId: string, product: string): Promise<PriceInfo> {
  if (!customerId || !product) return { price: 0, source: null, list_name: null };
  const d = await postJSON("/api/customer/price", { customer_id: customerId, product });
  return { price: d.price || 0, source: d.source || null, list_name: d.list_name || null };
}

/** Tạo hoá đơn KiotViet cho đơn (tương đương lệnh 'tạo hd'). */
export async function createKiotVietInvoice(threadId: string | number): Promise<any> {
  return postJSON("/api/order/invoice/create-kiotviet", { thread_id: Number(threadId) });
}

/** Xoá hoá đơn KiotViet (chỉ admin 'duy'). */
export async function deleteKiotVietInvoice(threadId: string | number): Promise<any> {
  const u = currentUser();
  return postJSON("/api/order/invoice/delete-kiotviet", { thread_id: Number(threadId), user_id: u?.username });
}

/** Kéo nợ KiotViet mới nhất của khách về làm snapshot nợ của đơn. */
export async function refreshOrderDebt(threadId: string | number): Promise<any> {
  return postJSON("/api/order/refresh-debt", { thread_id: Number(threadId) });
}

/** Xoá đơn (admin) — chỉ được khi KHÔNG có HĐ KiotViet + KHÔNG còn phân bổ kho. */
export async function deleteOrder(threadId: string | number): Promise<any> {
  return delJSON(`/api/order/${threadId}`);
}

/** Lịch sử thao tác toàn bộ (mọi đơn/phiếu/thùng), cursor theo id (before). */
export async function getActivity(before?: number | null): Promise<{ items: any[]; has_more: boolean; next_before: number | null }> {
  return getJSON(`/api/activity${before ? `?before=${before}` : ""}`, { cache: false });
}

/** Đơn theo ngày giao trong 1 tháng (YYYY-MM) — cho lịch giao. Rows compact. */
export async function getDeliveryOrders(month: string): Promise<{ month: string; orders: any[] }> {
  const d = await getJSON(`/api/orders/delivery?month=${encodeURIComponent(month)}`, { cache: false });
  return { month: d.month, orders: d.orders || [] };
}

/** Đặt ngày giao dự kiến ('YYYY-MM-DDTHH:MM' hoặc '' để xoá). */
export async function setOrderNgayGiao(threadId: string | number, ngayGiao: string): Promise<{ ngay_giao: string | null }> {
  const d = await postJSON("/api/order/ngay-giao", { thread_id: Number(threadId), ngay_giao: ngayGiao || null });
  return { ngay_giao: d.ngay_giao ?? null };
}

/** URL HTML hoá đơn để mở tab mới (kèm token cho WebView/khi bật auth). */
export function invoiceHtmlUrl(threadId: string | number): string {
  const t = getToken();
  return `${serverUrl()}/api/order/${Number(threadId)}/invoice-html${t ? `?token=${encodeURIComponent(t)}` : ""}`;
}

// ── Ảnh đính kèm đơn ─────────────────────────────────────────────────────────

/** Header chỉ có Authorization (KHÔNG set Content-Type — để browser tự gắn
 *  multipart boundary cho FormData). */
function authHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

/** POST multipart/form-data (upload ảnh). Không queue offline — cần mạng. */
export async function postForm(path: string, form: FormData): Promise<any> {
  const url = serverUrl() + path;
  try {
    const res = await fetch(url, { method: "POST", headers: authHeaders(), body: form });
    return await parse(res);
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new Error("Mất mạng — tải ảnh cần mạng, thử lại sau");
  }
}

/** DELETE JSON. */
export async function delJSON(path: string): Promise<any> {
  const url = serverUrl() + path;
  try {
    const res = await fetch(url, { method: "DELETE", headers: headers() });
    return await parse(res);
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new Error("Mất mạng — thao tác này cần mạng, thử lại sau");
  }
}

/** URL 1 ảnh của đơn (size 'thumb' | 'full'), kèm token cho <img src>. */
export function orderImageUrl(threadId: string | number, imageId: number, size: "thumb" | "full" = "full"): string {
  const t = getToken();
  const q = `?size=${size}${t ? `&token=${encodeURIComponent(t)}` : ""}`;
  return `${serverUrl()}/api/order/${Number(threadId)}/images/${imageId}/file${q}`;
}

export type OrderImage = { id: number; width: number; height: number; size: number; uploaded_by: string; kind?: string; created_at: number   /** xoá mềm: vẫn hiển thị, webapp vẽ dấu X đè lên */
  deleted_at?: number | null; deleted_by?: string | null;
};

/** Đổi loại ảnh đơn (soạn hàng / nộp tiền / hoá đơn / khác). base = '/api/order/<id>'. */
export async function setImageKind(base: string, imageId: number, kind: string): Promise<any> {
  return postJSON(`${base}/images/${imageId}/kind`, { kind }, { queueable: false });
}

export type ImageComment = { id: number; image_id: number; username: string; text: string; created_at: number };

/** Bình luận của 1 ảnh (cũ→mới). base = '/api/order/<id>'. */
export async function listImageComments(base: string, imageId: number): Promise<ImageComment[]> {
  const d = await getJSON(`${base}/images/${imageId}/comments`, { cache: false });
  return d.comments || [];
}
export async function addImageComment(base: string, imageId: number, text: string): Promise<ImageComment> {
  const d = await postJSON(`${base}/images/${imageId}/comments`, { text }, { queueable: false });
  return d.comment;
}
export async function deleteImageComment(base: string, imageId: number, commentId: number): Promise<any> {
  return delJSON(`${base}/images/${imageId}/comments/${commentId}`);
}

// ── Media DÙNG CHUNG (comments+ảnh) — base là gốc API, vd '/api/order/123' hoặc
//    '/api/media/production/123' / '/api/media/box/5'. Dùng bởi Comments/Images/… ──
export function mediaImageUrl(base: string, imageId: number, size: "thumb" | "full" = "full"): string {
  const t = getToken();
  const q = `?size=${size}${t ? `&token=${encodeURIComponent(t)}` : ""}`;
  return `${serverUrl()}${base}/images/${imageId}/file${q}`;
}
export async function listMediaImages(base: string): Promise<OrderImage[]> {
  const d = await getJSON(`${base}/images`, { cache: false });
  return d.images || [];
}
export async function deleteMediaImage(base: string, imageId: number): Promise<any> {
  return delJSON(`${base}/images/${imageId}`);
}

/** Liệt kê ảnh của đơn (mới nhất trước). */
export async function listOrderImages(threadId: string | number): Promise<OrderImage[]> {
  const d = await getJSON(`/api/order/${Number(threadId)}/images`, { cache: false });
  return d.images || [];
}

/** Xoá 1 ảnh của đơn. */
export async function deleteOrderImage(threadId: string | number, imageId: number): Promise<any> {
  return delJSON(`/api/order/${Number(threadId)}/images/${imageId}`);
}

/** Bảo đảm gallery có ảnh HĐ KiotViet — chưa có thì server render PNG ngay (~2s). */
export async function ensureInvoiceImage(threadId: string | number): Promise<OrderImage> {
  const d = await postJSON(`/api/order/${Number(threadId)}/invoice-image/ensure`, {});
  return d.image;
}

// ── Phiếu sản xuất (production) ───────────────────────────────────────────────

/** Số kiểu vi-VN (dấu chấm ngăn nghìn) — khớp _so() phía server. */
export function soVN(n: number | null | undefined): string {
  const v = Number(n);
  if (!isFinite(v)) return String(n ?? "");
  return v.toLocaleString("vi-VN");
}

/** Ngày tạo phiếu — ưu tiên field date, fallback parse date_code (YYYYMMDDHHMMSS).
 *  date_code luôn được set lúc tạo nên luôn có ngày để hiện. */
export function prodCreated(slip: { date?: string | null; date_code?: string | null }): string {
  if (slip.date) return slip.date;
  const dc = slip.date_code || "";
  if (dc.length < 8) return "";
  const [y, mo, d, h, mi] = [dc.slice(0, 4), dc.slice(4, 6), dc.slice(6, 8), dc.slice(8, 10), dc.slice(10, 12)];
  return h ? `${d}/${mo}/${y} ${h}:${mi}` : `${d}/${mo}/${y}`;
}

export type ProdSlip = {
  thread_id: number;
  date?: string;
  date_code?: string;
  sp_name?: string | null;
  sp_mam?: number | null;
  sp_luong?: number | null;
  sx_target?: number | null;
  total: number;
  ghi_chu?: string | null;
  kind?: "san_xuat" | "dong_goi";
  box_count?: number;   // số thùng đã tạo từ phiếu — >0 thì khoá đổi loại + cấm xoá
  report_total?: number;                                // tổng SP theo báo cáo thợ
  report_workers?: { name: string; tong: number }[];    // tổng SP từng thợ (giảm dần)
  report_notes?: { name: string; note: string }[];      // thợ 0 sản lượng nhưng có ghi chú
  boxed_total?: number;                                 // Σ quantity thùng nhập từ UI (bỏ số nhập tay)
  numbers?: { amount: number; note?: string; at?: string; by?: string }[];
  bang?: any | null;
  updated_at?: string;
  target?: number | null;
  pct?: number | null;
};

export type ProdCatalogItem = { code: string; mam: number | null; luong: number | null; cay_1_chao: number | null };

export type ProdReport = {
  product_code: string | null;
  so_cay_1_mam: number;
  date?: string | null;
  start?: string | null;
  end?: string | null;
  grand_total: number;
  rows: { name: string; so_gach: number; so_tru: number; so_cay_le: number; note: string; so_mam: number; tong_calc: number; sp_de?: number | null; mam_de?: number | null }[];
};

export type ProdListResp = { slips: ProdSlip[]; total: number; page: number; total_pages: number };

export async function listProduction(page = 1, kind?: "san_xuat" | "dong_goi"): Promise<ProdListResp> {
  const d = await getJSON(`/api/production?page=${page}${kind ? `&kind=${kind}` : ""}`);
  return { slips: d.slips || [], total: d.total || 0, page: d.page || 1, total_pages: d.total_pages || 1 };
}

export async function getProduction(id: string | number): Promise<ProdSlip | null> {
  const d = await getJSON(`/api/production/${id}`);
  return d.slip || null;
}

export async function productionCatalog(): Promise<ProdCatalogItem[]> {
  const d = await getJSON("/api/production/catalog");
  return d.products || [];
}

/** Tạo phiếu mới (mở forum topic ở group SX). Trả thread_id. */
export async function createProduction(product?: string): Promise<number> {
  const d = await postJSON("/api/production", { product: product || null });
  return d.thread_id;
}

export async function setProductionProduct(id: string | number, product: string): Promise<any> {
  return postJSON(`/api/production/${id}/product`, { product });
}

export async function setProductionTarget(id: string | number, target: number): Promise<any> {
  return postJSON(`/api/production/${id}/target`, { target });
}

export async function setProductionKind(id: string | number, kind: "san_xuat" | "dong_goi"): Promise<any> {
  return postJSON(`/api/production/${id}/kind`, { kind });
}
export async function setProductionNote(id: string | number, note: string): Promise<any> {
  return postJSON(`/api/production/${id}/note`, { note });
}

/** Nhập số lượng đã nhận (queueable: an toàn khi mất mạng). Kèm tên người nhập. */
export async function addProductionNumber(id: string | number, amount: number, note: string): Promise<any> {
  const u = currentUser();
  const user = u?.display_name || u?.username || "";
  return postJSON(`/api/production/${id}/number`, { amount, note, user }, { queueable: true });
}

/** Xem trước báo cáo (parse + compute, không lưu). */
export async function parseProductionReport(id: string | number, text: string): Promise<ProdReport> {
  return postJSON(`/api/production/${id}/report/parse`, { text });
}

export type SheetStatus = {
  ok: boolean;
  disabled?: boolean;
  error?: string;
  tab?: string;
  rows?: number;
  replaced?: boolean;
};

/** Lưu báo cáo. Trả kèm trạng thái đẩy Google Sheet (sheet). */
export async function saveProductionReport(
  id: string | number,
  text: string,
  sid?: string,
): Promise<ProdReport & { sheet?: SheetStatus }> {
  const u = currentUser();
  return postJSON(`/api/production/${id}/report`, { text, user: u?.display_name || u?.username || "", sid: sid || "" });
}

export async function deleteProduction(id: string | number): Promise<any> {
  return delJSON(`/api/production/${id}`);
}

// ── Danh sách thợ (template báo cáo) ──
export type Worker = { id: number; name: string; is_default: boolean; sort_order: number };
export async function listWorkers(): Promise<{ workers: Worker[]; defaults: string[] }> {
  const d = await getJSON("/api/workers", { cache: false });
  return { workers: d.workers || [], defaults: d.defaults || [] };
}
export async function addWorker(name: string, isDefault: boolean): Promise<Worker> {
  const d = await postJSON("/api/workers", { name, is_default: isDefault });
  return d.worker;
}
export async function updateWorker(id: number, patch: { name?: string; is_default?: boolean }): Promise<Worker> {
  const d = await postJSON(`/api/workers/${id}`, patch);
  return d.worker;
}
export async function deleteWorker(id: number): Promise<any> {
  return delJSON(`/api/workers/${id}`);
}
// Sắp lại thứ tự thợ (sort_order) theo mảng ids → ảnh hưởng template báo cáo
export async function reorderWorkers(ids: number[]): Promise<{ workers: Worker[]; defaults: string[] }> {
  const d = await postJSON("/api/workers/reorder", { ids });
  return { workers: d.workers || [], defaults: d.defaults || [] };
}

const _actor = () => { const u = currentUser(); return u?.display_name || u?.username || ""; };

/** Khoá sửa báo cáo (1 người/phiếu). Trả {holder, mine}. Gọi lặp lại = heartbeat gia hạn. */
// sid = mã phiên mỗi tab/máy — cùng tài khoản mở 2 máy vẫn chỉ 1 máy giữ khoá sửa
export async function lockReport(id: string | number, sid: string): Promise<{ ok: boolean; holder: string | null; mine: boolean }> {
  return postJSON(`/api/production/${id}/report/lock`, { user: _actor(), sid });
}
export async function unlockReport(id: string | number, sid: string): Promise<any> {
  return postJSON(`/api/production/${id}/report/unlock`, { user: _actor(), sid });
}
/** Ai đang giữ khoá sửa báo cáo (không xin khoá) — badge ở trang chi tiết phiếu. */
export async function reportLockStatus(id: string | number): Promise<string | null> {
  const d = await getJSON(`/api/production/${id}/report/lock`, { cache: false });
  return d.holder ?? null;
}
export type ProdDashboard = {
  totals: { tong: number; phieu: number; tho: number };
  by_worker: { name: string; tong: number; phieu: number; mam: number }[];
  by_day: { ymd: string; tong: number; phieu: number }[];
  by_product: { code: string; tong: number; phieu: number }[];
};
export async function getProductionDashboard(from?: string, to?: string): Promise<ProdDashboard> {
  const qs = new URLSearchParams();
  if (from) qs.set("from", from);
  if (to) qs.set("to", to);
  const q = qs.toString();
  return getJSON(`/api/production/report-dashboard${q ? "?" + q : ""}`, { cache: false });
}

export type WorkerReportRow = { thread_id: number; product_code: string; date: string; ymd: string; so_mam: number; tong_calc: number; note: string };
export type WorkerReport = { name: string; total: number; total_mam: number; phieu: number; rows: WorkerReportRow[] };
export async function getWorkerReport(name: string, from?: string, to?: string): Promise<WorkerReport> {
  const qs = new URLSearchParams();
  if (from) qs.set("from", from);
  if (to) qs.set("to", to);
  const q = qs.toString();
  return getJSON(`/api/production/worker/${encodeURIComponent(name)}${q ? "?" + q : ""}`, { cache: false });
}

/** Gửi bản nháp bảng (người đang sửa) → người xem thấy trực tiếp. Không lưu. */
export async function pushReportDraft(id: string | number, draft: { rows: any[]; date?: string; start?: string; end?: string }, sid?: string): Promise<any> {
  return postJSON(`/api/production/${id}/report/draft`, { ...draft, user: _actor(), sid: sid || "" });
}

// ── Sổ quỹ (cash book) ────────────────────────────────────────────────────────

export type QuyReceipt = {
  id: number;
  type: "thu" | "chi";
  amount: number;
  note?: string | null;
  source: "manual" | "order";
  order_thread_id?: number | null;
  payment_id?: string | null;
  customer_key?: string | null;
  customer_name?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  date?: string | null;
};
export type QuySummary = { thu: number; chi: number; balance: number; count: number };
export type QuyRange = { from?: string; to?: string };
export type QuyListResp = {
  receipts: QuyReceipt[];
  total: number;
  page: number;
  total_pages: number;
  summary: QuySummary; // toàn sổ (số dư quỹ thật)
  period: QuySummary;  // tổng trong kỳ đang lọc (= summary nếu không lọc ngày)
  from: string | null;
  to: string | null;
};

export async function listQuy(page = 1, type?: "thu" | "chi", range?: QuyRange, q?: string): Promise<QuyListResp> {
  const qs = new URLSearchParams({ page: String(page) });
  if (type) qs.set("type", type);
  if (q) qs.set("q", q);
  if (range?.from) qs.set("from", range.from);
  if (range?.to) qs.set("to", range.to);
  const d = await getJSON(`/api/quy?${qs.toString()}`, { cache: false });
  const empty = { thu: 0, chi: 0, balance: 0, count: 0 };
  return {
    receipts: d.receipts || [],
    total: d.total || 0,
    page: d.page || 1,
    total_pages: d.total_pages || 1,
    summary: d.summary || empty,
    period: d.period || d.summary || empty,
    from: d.from ?? null,
    to: d.to ?? null,
  };
}

/** Tạo phiếu thu/chi tay. Trả receipt mới. */
export async function createQuy(type: "thu" | "chi", amount: number, note: string): Promise<QuyReceipt> {
  const d = await postJSON("/api/quy", { type, amount, note });
  return d.receipt;
}

export async function deleteQuy(id: number | string): Promise<any> {
  return delJSON(`/api/quy/${id}`);
}

// ── Quản lý user (chỉ admin) ──────────────────────────────────────────────────

export type WebUser = { username: string; display_name: string; role: string; disabled: boolean };

export async function listUsers(): Promise<{ users: WebUser[]; roles: string[] }> {
  const d = await getJSON("/api/users", { cache: false });
  return { users: d.users || [], roles: d.roles || ["staff", "van_phong", "admin"] };
}
export async function createUser(username: string, pin: string, display_name: string, role: string): Promise<any> {
  return postJSON("/api/users", { username, pin, display_name, role });
}
export async function setUserRole(username: string, role: string): Promise<any> {
  return postJSON(`/api/users/${encodeURIComponent(username)}/role`, { role });
}
export async function setUserDisabled(username: string, disabled: boolean): Promise<any> {
  return postJSON(`/api/users/${encodeURIComponent(username)}/disabled`, { disabled });
}
export async function setUserPin(username: string, pin: string): Promise<any> {
  return postJSON(`/api/users/${encodeURIComponent(username)}/pin`, { pin });
}

export const ROLE_LABEL: Record<string, string> = { admin: "Admin", van_phong: "Văn phòng", staff: "Nhân viên" };

// ── Notification center ───────────────────────────────────────────────────────

export type Notif = {
  id: number;
  type: string;
  title: string;
  body: string;
  thread_id?: number | null;
  focus?: string | null;
  created_at?: string | null;
};

export async function listNotifications(limit = 30): Promise<{ notifications: Notif[]; latest_id: number }> {
  const d = await getJSON(`/api/notifications?limit=${limit}`, { cache: false });
  return { notifications: d.notifications || [], latest_id: d.latest_id || 0 };
}

// ── Kho thùng (inventory) ─────────────────────────────────────────────────────

export type InvBox = {
  id: number;
  product_code: string;
  box_code: string;
  quantity: number;
  status: string;
  source_thread_id?: number | null;
  order_thread_id?: number | null;
  note?: string | null;
  mfg_date?: string | null;
  disabled?: number | boolean | null;
  disabled_reason?: string | null;
  created_at?: string;
  created_by?: string;
  allocated?: number; // tổng đã xuất cho các đơn
  remaining?: number; // còn lại = quantity - allocated
  place_id?: number | null;
  place_name?: string | null;
  unit_id?: number | null;
  unit_name?: string | null;
  product_unit?: string;
};

export type Unit = { id: number; name: string; box_count?: number };
/** Danh sách đơn vị chứa (Thùng/Bọc/Cây/Kiện/Kệ…). */
export async function listUnits(): Promise<Unit[]> {
  const d = await getJSON("/api/units", { cache: false });
  return d.units || [];
}
export async function createUnit(name: string): Promise<Unit> {
  const d = await postJSON("/api/units", { name }, { queueable: false });
  return d.unit;
}
export async function deleteUnit(id: number): Promise<any> {
  return delJSON(`/api/units/${id}`);
}
/** Xoá HẲN 1 thùng (chỉ admin; cấm nếu đã xuất cho đơn). */
export async function deleteBox(id: number | string): Promise<any> {
  return delJSON(`/api/inventory/box/${id}`);
}
/** Đổi đơn vị chứa của 1 thùng. */
export async function setBoxUnit(boxId: number, unitId: number): Promise<InvBox | null> {
  const d = await postJSON(`/api/inventory/box/${boxId}`, { unit_id: unitId }, { queueable: false });
  return d.ok ? d.box : null;
}

export type Place = { id: number; name: string; note?: string; box_count?: number; thumb_image_id?: number | null };
/** Danh sách vị trí kho (Kho A, Kho B…). */
export async function listPlaces(): Promise<Place[]> {
  const d = await getJSON("/api/places", { cache: false });
  return d.places || [];
}
export async function createPlace(name: string, note = ""): Promise<Place> {
  const d = await postJSON("/api/places", { name, note }, { queueable: false });
  return d.place;
}
export async function renamePlace(id: number, name: string): Promise<Place> {
  const d = await postJSON(`/api/places/${id}`, { name }, { queueable: false });
  return d.place;
}
export async function setPlaceNote(id: number, note: string): Promise<Place> {
  const d = await postJSON(`/api/places/${id}`, { note }, { queueable: false });
  return d.place;
}
export async function deletePlace(id: number): Promise<any> {
  return delJSON(`/api/places/${id}`);
}
/** Đặt/gỡ vị trí kho cho 1 thùng (placeId=null → gỡ). */
export async function setBoxPlace(boxId: number, placeId: number | null): Promise<InvBox | null> {
  const d = await postJSON(`/api/inventory/box/${boxId}`, { place_id: placeId }, { queueable: false });
  return d.ok ? d.box : null;
}

export type Allocation = {
  allocation_id: number;
  quantity: number; // phần lấy từ thùng
  box_id: number;
  box_code: string;
  product_code: string;
  box_quantity?: number;
  kind?: string;   // 'order' | 'production' (tiêu hao nguyên liệu)
  box_remaining?: number;
  mfg_date?: string | null;
  order_thread_id?: number;
  allocated_by?: string;
  order_text?: string; // dòng đầu nội dung đơn (sneak peek, chỉ trang chi tiết thùng)
};
export type InvGroup = { quantity: number; count: number; total: number; box_codes: string[] };
export type InvProductLink = { code: string; name: string; cost_price: number; unit?: string; kv_id: number | null; kv_full_name: string | null; kv_synced_at: string | null; linked: boolean };
export type InvOrderRef = { thread_id: number; text: string; sl: number | null; price: number | null; created: string | null };
export type InvDetail = {
  product_code: string;
  total: number;
  box_count: number;
  groups: InvGroup[];
  boxes: InvBox[]; // in_stock
  all_boxes: InvBox[]; // mọi status
  product: InvProductLink | null; // liên kết KiotViet + tên danh mục
};
export type InvProductSummary = {
  product_code: string;
  name?: string;
  linked?: boolean;
  in_stock_total: number;
  in_stock_count: number;
  allocated_count: number;
  shipped_count: number;
  total_count: number;
  unit?: string;
};

/** Nhập 1 đợt = N thùng (mỗi thùng số cây tự do). Mã tự sinh. Queueable (offline). */
// ── Cài đặt hệ thống (admin toggle) ──
export type AppSettings = Record<string, boolean>;
export async function getAppSettings(): Promise<AppSettings> {
  const d = await getJSON("/api/settings", { cache: false });
  return d.settings || {};
}
export async function setAppSetting(key: string, value: boolean): Promise<AppSettings> {
  const d = await postJSON("/api/settings", { key, value });
  return d.settings || {};
}

/** Chốt/huỷ chốt xuất kho cho đơn (huỷ = admin). */
export async function stockConfirmOrder(id: string | number, confirm: boolean): Promise<{ stock_confirmed: { at?: string; by?: string } | null }> {
  return postJSON(`/api/order/${id}/stock-confirm`, { confirm });
}

export async function addProductionBoxes(
  id: string | number,
  boxes: { quantity: number }[],
  note = "",
  mfgDate = "",
  unitId?: number | null,
  consume?: { box_id: number; quantity: number }[],
  productCode?: string,
  placeId?: number | null
): Promise<{ boxes: InvBox[]; total: number; consumed?: any[]; _queued?: boolean }> {
  const u = currentUser();
  const user = u?.display_name || u?.username || "";
  const d = await postJSON(
    `/api/production/${id}/boxes`,
    { boxes, note, mfg_date: mfgDate, user, unit_id: unitId || null, consume: consume || [], product_code: productCode || null, place_id: placeId || null },
    { queueable: true }
  );
  return { boxes: d.boxes || [], total: d.total, consumed: d.consumed, _queued: d._queued };
}

/** Các thùng đã nhập ở 1 phiếu SX (mọi status). */
export async function slipBoxes(id: string | number): Promise<InvBox[]> {
  const d = await getJSON(`/api/production/${id}/boxes`);
  return d.boxes || [];
}

/** Dashboard kho: mỗi product tồn + số thùng đã xuất/đã giao. */
export async function inventoryList(): Promise<InvProductSummary[]> {
  const d = await getJSON("/api/inventory");
  return d.products || [];
}

export type KhoBox = { id: number; product_code: string; box_code: string; quantity: number; remaining: number; allocated: number; disabled: boolean; note: string; mfg_date?: string | null; created_at?: string; place_id?: number | null; place_name?: string | null; unit_id?: number | null; unit_name?: string | null; product_unit?: string; source_thread_id?: number | null };

// ── Công thức sản xuất (BOM): SP cần nguyên liệu theo tỉ lệ ──
export type RecipeLine = { id: number; ingredient_code: string; ratio: number; stock?: number; unit?: string };
export async function getRecipe(code: string): Promise<{ recipe: RecipeLine[]; unit: string }> {
  const d = await getJSON(`/api/products/${encodeURIComponent(code)}/recipe`, { cache: false });
  return { recipe: d.recipe || [], unit: d.unit || "cây" };
}
export async function setRecipeLine(code: string, ingredientCode: string, ratio: number): Promise<RecipeLine> {
  const d = await postJSON(`/api/products/${encodeURIComponent(code)}/recipe`, { ingredient_code: ingredientCode, ratio }, { queueable: false });
  return d.line;
}
export async function deleteRecipeLine(code: string, id: number): Promise<any> {
  return delJSON(`/api/products/${encodeURIComponent(code)}/recipe/${id}`);
}
/** Kho hàng: MỌI thùng của MỌI sản phẩm (dashboard kho trực quan). */
export async function allBoxes(): Promise<KhoBox[]> {
  const d = await getJSON("/api/inventory/boxes", { cache: false });
  return d.boxes || [];
}

/** Tồn 1 product: tổng + nhóm size + thùng in_stock (boxes) + mọi thùng (all_boxes). */
export async function inventoryDetail(code: string): Promise<InvDetail> {
  const d = await getJSON(`/api/inventory/${encodeURIComponent(code)}`);
  return {
    product_code: d.product_code,
    total: d.total || 0,
    box_count: d.box_count || 0,
    groups: d.groups || [],
    boxes: d.boxes || [],
    all_boxes: d.all_boxes || [],
    product: d.product || null,
  };
}

/** Lazy: các đơn có mã SP này (phân trang). */
export async function productOrders(code: string, offset = 0, limit = 20): Promise<{ orders: InvOrderRef[]; total: number; has_more: boolean }> {
  const d = await getJSON(`/api/inventory/${encodeURIComponent(code)}/orders?offset=${offset}&limit=${limit}`, { cache: false });
  return { orders: d.orders || [], total: d.total || 0, has_more: !!d.has_more };
}

export type KvProduct = { id: number; code: string; full_name: string };

/** Tạo mã SP mới (danh mục local). */
export async function createProduct(code: string, name = "", unit = ""): Promise<{ product: InvProductLink; existed: boolean }> {
  const d = await postJSON("/api/products", { code, name, unit }, { queueable: false });
  return { product: d.product, existed: !!d.existed };
}
/** Sửa SP (đơn vị / tên / ghi chú). */
export async function updateProduct(code: string, patch: { unit?: string; name?: string; note?: string }): Promise<InvProductLink | null> {
  const d = await postJSON(`/api/products/${encodeURIComponent(code)}`, patch, { queueable: false });
  return d.ok ? d.product : null;
}
/** Đổi MÃ SP (admin) — mọi liên kết theo id tự đúng; KiotViet đổi theo best-effort. */
export async function renameProduct(code: string, newCode: string): Promise<{ product: InvProductLink & { code: string }; kiotviet?: string | null }> {
  const d = await postJSON(`/api/products/${encodeURIComponent(code)}/rename`, { new_code: newCode }, { queueable: false });
  return { product: d.product, kiotviet: d.kiotviet };
}
export type KvCategory = { id: number; name: string };
/** Nhóm hàng KiotViet (chọn khi tạo SP mới). */
export async function kiotvietCategories(): Promise<KvCategory[]> {
  const d = await getJSON("/api/kiotviet/categories", { cache: false });
  return d.categories || [];
}
/** Tạo SP MỚI trên KiotViet từ mã local (tên/đơn vị local) rồi liên kết. Admin. */
export async function createKiotvietProduct(code: string, patch: { category_id: number; name?: string; unit?: string; base_price?: number }): Promise<InvProductLink | null> {
  const d = await postJSON(`/api/products/${encodeURIComponent(code)}/kiotviet-create`, patch, { queueable: false });
  return d.ok ? d.product : null;
}
/** Tìm sản phẩm KiotViet để liên kết (từng cái). */
export async function searchKiotvietProducts(q: string): Promise<KvProduct[]> {
  const d = await getJSON(`/api/products/kiotviet?q=${encodeURIComponent(q)}`, { cache: false });
  return d.products || [];
}
/** Liên kết 1 mã SP với 1 sản phẩm KiotViet. */
export async function linkProductKiotviet(code: string, kvId: number, fullName: string): Promise<InvProductLink> {
  const d = await postJSON(`/api/products/${encodeURIComponent(code)}/link`, { kv_id: kvId, kv_full_name: fullName }, { queueable: false });
  return d.product;
}
/** Bỏ liên kết KiotViet. */
export async function unlinkProductKiotviet(code: string): Promise<InvProductLink> {
  const d = await postJSON(`/api/products/${encodeURIComponent(code)}/unlink`, {}, { queueable: false });
  return d.product;
}
/** Xoá 1 mã SP khỏi danh mục local (admin). */
export async function deleteProduct(code: string): Promise<any> {
  return delJSON(`/api/products/${encodeURIComponent(code)}`);
}

export type InvSourceSlip = { thread_id: number; date?: string | null; sp_name?: string | null };
export type InvBoxDetail = { box: InvBox; source_slip: InvSourceSlip | null; allocations: Allocation[];
  packed_materials?: { code: string; amount: number }[] };

/** Chi tiết 1 thùng: info + còn lại + phiếu SX nguồn + các đơn đã xuất. */
export async function boxDetail(id: string | number): Promise<InvBoxDetail | null> {
  const d = await getJSON(`/api/inventory/box/${id}`);
  return d.ok ? { box: d.box, source_slip: d.source_slip, allocations: d.allocations || [],
    packed_materials: d.packed_materials || [] } : null;
}

/** Chuyển hàng giữa 2 thùng CÙNG mã SP (bút toán kép — tồn tổng không đổi). */
export async function transferBox(fromId: number | string, toId: number, quantity: number): Promise<any> {
  const d = await postJSON(`/api/inventory/box/${fromId}/transfer`, { to_box_id: toId, quantity }, { queueable: false });
  return d.transfer;
}

/** Vô hiệu / kích hoạt lại 1 thùng (vô hiệu cần lý do). */
export async function setBoxDisabled(
  id: string | number,
  disabled: boolean,
  reason = ""
): Promise<InvBox | null> {
  const d = await postJSON(`/api/inventory/box/${id}/disable`, { disabled, reason });
  return d.ok ? d.box : null;
}

/** Sửa ghi chú / số cây của 1 thùng. */
export async function updateBox(
  id: string | number,
  patch: { note?: string; quantity?: number; mfg_date?: string }
): Promise<InvBox | null> {
  const d = await postJSON(`/api/inventory/box/${id}`, patch);
  return d.ok ? d.box : null;
}

/** Các phần thùng đã xuất cho đơn này (1 dòng = 1 phần thùng). */
export async function orderAllocations(id: string | number): Promise<Allocation[]> {
  const d = await getJSON(`/api/order/${id}/allocations`);
  return d.allocations || [];
}

/** Xuất kho cho đơn — lấy 1 phần được: picks=[{box_id, quantity?}] (thiếu qty = hết còn lại). */
export async function allocatePicks(
  id: string | number,
  picks: { box_id: number; quantity?: number | null }[]
): Promise<Allocation[]> {
  const u = currentUser();
  const user = u?.display_name || u?.username || "";
  const d = await postJSON(`/api/order/${id}/allocate`, { picks, user });
  return d.allocations || [];
}

/** Thu hồi phần thùng khỏi đơn (theo allocation_ids). Trả list phần còn của đơn. */
export async function releaseAllocations(id: string | number, allocationIds: number[]): Promise<Allocation[]> {
  const d = await postJSON(`/api/order/${id}/release`, { allocation_ids: allocationIds });
  return d.allocations || [];
}

// ── VIỆC (task list — bảng web_tasks + mirror task đơn) ──
export type Task = {
  id: number; kind: "free" | "order_step" | "order_custom";
  thread_id?: number | null; step_key?: string | null;
  title: string; note: string; order_label: string; order_text?: string;
  assignee: string; due_at?: string | null;
  done: boolean; done_by?: string | null; done_at?: number | null;
  created_by: string; created_at: number; updated_at: number;
};
export type TaskCounts = { open: number; free: number; order: number; extra: number; mine: number; overdue: number; done: number };

export async function listTasks(filter: string, page = 1, q = "", assignee = ""): Promise<{ tasks: Task[]; total: number; total_pages: number; counts: TaskCounts; today: string }> {
  const me = currentUser()?.username || "";
  const d = await getJSON(`/api/tasks?filter=${encodeURIComponent(filter)}&page=${page}&me=${encodeURIComponent(me)}${q ? `&q=${encodeURIComponent(q)}` : ""}${assignee ? `&assignee=${encodeURIComponent(assignee)}` : ""}`, { cache: false });
  return { tasks: d.tasks || [], total: d.total || 0, total_pages: d.total_pages || 1, counts: d.counts, today: d.today || "" };
}
export async function getTask(id: number): Promise<Task> {
  return (await getJSON(`/api/tasks/${id}`, { cache: false })).task;
}
export async function createTask(body: { title: string; note?: string; assignee?: string; due_at?: string; thread_id?: number }): Promise<Task> {
  return (await postJSON("/api/tasks", body)).task;
}
export async function updateTask(id: number, body: any): Promise<Task> {
  return (await postJSON(`/api/tasks/${id}`, body)).task;
}
export async function deleteTask(id: number): Promise<void> {
  const res = await fetch(`/api/tasks/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${getToken()}` } });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(d.error || "Xoá thất bại");
}
export async function taskDays(): Promise<{ d: string; o: number; p: number }[]> {
  return (await getJSON("/api/tasks?days=1", { cache: false })).days || [];
}
export async function taskDay(day: string): Promise<Task[]> {
  return (await getJSON(`/api/tasks?day=${encodeURIComponent(day)}`, { cache: false })).tasks || [];
}
export async function taskAssignees(): Promise<{ username: string; display_name: string; open: number }[]> {
  return (await getJSON("/api/tasks/assignees", { cache: false })).users || [];
}
