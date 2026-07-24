// Popup BẢNG GIÁ của 1 khách — modal dùng chung (CreateOrder + OrderInvoiceEdit).
// Tự fetch /api/customers/{key}/price-list khi mount; parent render có điều kiện:
//   {plCust && <PriceListModal customerId={plCust} onClose={...} />}
import { useEffect, useState } from "preact/hooks";
import { getCustomerPriceList, type CustomerPriceList } from "../api";
import { money } from "../format";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";
import { ErrorState, LoadingInline } from "../ui/states";

export function PriceListModal({ customerId, onClose }: {
  customerId: string;
  onClose: () => void;
}) {
  const [priceList, setPriceList] = useState<CustomerPriceList | null>(null);
  const [err, setErr] = useState("");
  useScrollLock(true);           // khoá cuộn nền khi popup mở
  usePopupBack(true, onClose);   // nút BACK đóng popup trước
  const [tick, setTick] = useState(0);   // retry = bump để chạy lại effect
  useEffect(() => {
    setPriceList(null);
    setErr("");
    let alive = true;
    getCustomerPriceList(customerId)
      .then((r) => { if (alive) setPriceList(r); })
      .catch((e: any) => { if (alive) setErr(e?.message || "Không tải được bảng giá"); });
    return () => { alive = false; };
  }, [customerId, tick]);
  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head">
          <b><Icon name="clipboard" size={15} /> Bảng giá{priceList?.name ? `: ${priceList.name}` : ""}</b>
          <button class="btn small" title="Đóng" onClick={onClose}><Icon name="close" size={14} /></button>
        </div>
        {err ? (
          <ErrorState msg={err} onRetry={() => setTick((t) => t + 1)} />
        ) : !priceList ? (
          <p class="muted small"><LoadingInline /></p>
        ) : priceList.items.length ? (
          <div class="pl-scroll">
            <table class="invoice-table">
              <tbody>
                {priceList.items.map((it) => (
                  <tr key={it.sp}><td>{it.sp}</td><td class="num">{money(it.price)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p class="muted small">Bảng giá trống.</p>
        )}
      </div>
    </div>
  );
}
