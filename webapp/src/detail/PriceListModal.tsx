// Popup BẢNG GIÁ của 1 khách — modal dùng chung (CreateOrder + OrderInvoiceEdit).
// Tự fetch /api/customers/{key}/price-list khi mount; parent render có điều kiện:
//   {plCust && <PriceListModal customerId={plCust} onClose={...} />}
import { useEffect, useState } from "preact/hooks";
import { getCustomerPriceList, type CustomerPriceList } from "../api";
import { money } from "../format";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Icon } from "../ui/Icon";
import { LoadingInline } from "../ui/states";

export function PriceListModal({ customerId, onClose }: {
  customerId: string;
  onClose: () => void;
}) {
  const [priceList, setPriceList] = useState<CustomerPriceList | null>(null);
  useScrollLock(true);           // khoá cuộn nền khi popup mở
  usePopupBack(true, onClose);   // nút BACK đóng popup trước
  useEffect(() => {
    setPriceList(null);
    let alive = true;
    getCustomerPriceList(customerId).then((r) => { if (alive) setPriceList(r); }).catch(() => {});
    return () => { alive = false; };
  }, [customerId]);
  return (
    <div class="modal-backdrop" onClick={onClose}>
      <div class="modal" onClick={(e: any) => e.stopPropagation()}>
        <div class="row space">
          <b><Icon name="clipboard" size={15} /> Bảng giá{priceList?.name ? `: ${priceList.name}` : ""}</b>
          <button class="btn small" onClick={onClose}><Icon name="close" size={14} /></button>
        </div>
        {!priceList ? (
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
