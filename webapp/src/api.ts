// Lớp gọi API — gắn token, base URL cấu hình được (WebView trỏ Tailscale IP),
// cache GET (network-first, rớt mạng đọc cache) + hàng đợi POST offline (offline.ts).
import { flushQueue, queuePost, readCache, writeCache } from "./offline";

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
    const data = await parse(res);
    if (useCache) writeCache(path, data);
    return data;
  } catch (e) {
    if (e instanceof ApiError) throw e;
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
    return await parse(res);
  } catch (e) {
    if (e instanceof ApiError) throw e;
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

export type OrderImage = { id: number; width: number; height: number; size: number; uploaded_by: string; created_at: number };

/** Liệt kê ảnh của đơn (mới nhất trước). */
export async function listOrderImages(threadId: string | number): Promise<OrderImage[]> {
  const d = await getJSON(`/api/order/${Number(threadId)}/images`, { cache: false });
  return d.images || [];
}

/** Xoá 1 ảnh của đơn. */
export async function deleteOrderImage(threadId: string | number, imageId: number): Promise<any> {
  return delJSON(`/api/order/${Number(threadId)}/images/${imageId}`);
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
  rows: { name: string; so_gach: number; so_tru: number; so_cay_le: number; note: string; so_mam: number; tong_calc: number }[];
};

export type ProdListResp = { slips: ProdSlip[]; total: number; page: number; total_pages: number };

export async function listProduction(page = 1): Promise<ProdListResp> {
  const d = await getJSON(`/api/production?page=${page}`);
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
  text: string
): Promise<ProdReport & { sheet?: SheetStatus }> {
  return postJSON(`/api/production/${id}/report`, { text });
}

export async function deleteProduction(id: string | number): Promise<any> {
  return delJSON(`/api/production/${id}`);
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
};

export type Allocation = {
  allocation_id: number;
  quantity: number; // phần lấy từ thùng
  box_id: number;
  box_code: string;
  product_code: string;
  box_quantity?: number;
  box_remaining?: number;
  mfg_date?: string | null;
  order_thread_id?: number;
  allocated_by?: string;
};
export type InvGroup = { quantity: number; count: number; total: number; box_codes: string[] };
export type InvDetail = {
  product_code: string;
  total: number;
  box_count: number;
  groups: InvGroup[];
  boxes: InvBox[]; // in_stock
  all_boxes: InvBox[]; // mọi status
};
export type InvProductSummary = {
  product_code: string;
  in_stock_total: number;
  in_stock_count: number;
  allocated_count: number;
  shipped_count: number;
  total_count: number;
};

/** Nhập 1 đợt = N thùng (mỗi thùng số cây tự do). Mã tự sinh. Queueable (offline). */
export async function addProductionBoxes(
  id: string | number,
  boxes: { quantity: number }[],
  note = "",
  mfgDate = ""
): Promise<{ boxes: InvBox[]; total: number; _queued?: boolean }> {
  const u = currentUser();
  const user = u?.display_name || u?.username || "";
  const d = await postJSON(
    `/api/production/${id}/boxes`,
    { boxes, note, mfg_date: mfgDate, user },
    { queueable: true }
  );
  return { boxes: d.boxes || [], total: d.total, _queued: d._queued };
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
  };
}

export type InvSourceSlip = { thread_id: number; date?: string | null; sp_name?: string | null };
export type InvBoxDetail = { box: InvBox; source_slip: InvSourceSlip | null; allocations: Allocation[] };

/** Chi tiết 1 thùng: info + còn lại + phiếu SX nguồn + các đơn đã xuất. */
export async function boxDetail(id: string | number): Promise<InvBoxDetail | null> {
  const d = await getJSON(`/api/inventory/box/${id}`);
  return d.ok ? { box: d.box, source_slip: d.source_slip, allocations: d.allocations || [] } : null;
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
