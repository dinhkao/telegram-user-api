// Nội dung hộp xác nhận "Tạo hoá đơn KiotViet" — kèm tuỳ chọn ẨN DÒNG HÀNG TẶNG
// (đơn giá 0) trên HTML/ảnh hoá đơn. Chốt MỘT LẦN lúc bấm tạo: server lưu cờ vào
// đơn ($.invoice_hide_zero_price) nên mọi lần in/xem/gửi lại HĐ sau đều theo cờ này.
// Dùng ở pages/OrderDetail.tsx qua confirmDialog({ content }); vì hộp xác nhận trả
// về boolean nên trạng thái tick ghi vào object `opt` do trang cha giữ.
import { useState } from "preact/hooks";

export type CreateInvoiceOpt = { hideZero: boolean };

export function CreateInvoiceConfirm({ opt, zeroCount }: { opt: CreateInvoiceOpt; zeroCount: number }) {
  const [on, setOn] = useState(opt.hideZero);
  return (
    <div>
      <p style="margin:0 0 8px">Tạo hoá đơn KiotViet cho đơn này?</p>
      {zeroCount > 0 && (
        <label style="display:flex; align-items:center; gap:10px; justify-content:center; cursor:pointer">
          <span>Ẩn {zeroCount} dòng giá 0đ khi in hoá đơn</span>
          <span class={on ? "tgl on" : "tgl"} role="switch" aria-checked={on}
            onClick={() => { const v = !on; setOn(v); opt.hideZero = v; }}><span class="tgl-knob" /></span>
        </label>
      )}
    </div>
  );
}
