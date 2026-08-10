// Hướng dẫn KHO ĐẬU (hệ kho riêng) — dữ liệu tĩnh (xem guides/types.ts). Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_DAU: Guide[] = [
  {
    key: "kho-dau", icon: "box", cat: "Kho & hàng hoá",
    title: "Kho đậu",
    desc: "Theo dõi tồn đậu riêng: vị trí kho, danh mục đậu, phiếu nhập/xuất/điều chỉnh.",
    routes: ["#/kho-dau"],
    sections: [
      { title: "Dùng để làm gì?", html: `
        <p><a href="#/kho-dau">Kho đậu</a> là <b>một hệ kho riêng biệt</b>, không dính gì tới
        <a href="#/kho">📦 Kho hàng</a> (thùng kẹo, sản phẩm, phiếu sản xuất). Hàng hoá riêng,
        vị trí kho riêng, phiếu riêng — sửa bên này không ảnh hưởng bên kia.</p>
        <p>Dùng để biết <b>còn bao nhiêu đậu, nằm ở kho nào</b>, và mỗi lần nhập/xuất là bao nhiêu.</p>` },
      { title: "Thiết lập trước khi dùng", html: `
        <p>Vào <a href="#/kho-dau/thiet-lap">Thiết lập kho đậu</a> khai 2 danh mục:</p>
        <ul>
          <li><b>Vị trí kho</b> — Kho A, Kho B… mỗi chỗ chứa đậu là một dòng.</li>
          <li><b>Loại đậu</b> — tên + <b>đơn vị tính</b> (kg, bao, thùng…). Mọi số của loại
            đậu đó về sau đều tính theo đơn vị này.</li>
        </ul>
        <p class="muted small">Thêm mới: ai đăng nhập cũng làm được. Đổi tên/đơn vị: văn phòng.
        Xoá: admin, và chỉ xoá được khi chưa dính phiếu nào.</p>` },
      { title: "3 loại phiếu", html: `
        <ul>
          <li><b>Nhập kho</b> — đậu về kho. Số lượng <b>cộng</b> vào tồn.</li>
          <li><b>Xuất kho</b> — lấy đậu ra dùng/bán. Số lượng <b>trừ</b> khỏi tồn.
            Không xuất quá số đang có (hệ thống chặn).</li>
          <li><b>Điều chỉnh</b> — sau khi cân/đếm lại thực tế. Ô số nhập là
            <b>SỐ ĐẾM THỰC TẾ</b> (không phải phần chênh lệch) — hệ thống tự tính chênh
            lệch và đặt tồn về đúng số đếm.</li>
        </ul>
        <p>Mỗi phiếu thuộc <b>một kho</b> và có thể có <b>nhiều dòng đậu</b>. Bấm
        <b>Nhập / Xuất / Điều chỉnh</b> ở đầu trang <a href="#/kho-dau">Kho đậu</a> để tạo.</p>` },
      { title: "Xem tồn theo 2 kiểu", html: `
        <p>Ở trang <a href="#/kho-dau">Kho đậu</a> có nút gạt:</p>
        <ul>
          <li><b>Theo loại đậu</b> — mỗi loại đậu một dòng, kèm chia nhỏ đang nằm ở kho nào.</li>
          <li><b>Theo kho</b> — mỗi kho một dòng, kèm các loại đậu đang có trong kho đó.</li>
        </ul>
        <p class="muted small">Cùng một dữ liệu, chỉ đổi cách nhìn. Có ô tìm để lọc nhanh.</p>` },
      { title: "Sửa sai thì làm sao?", html: `
        <p>Phiếu <b>không sửa được</b> — ghi sai thì <b>xoá phiếu</b> (chỉ admin) rồi ghi lại,
        tồn tự hoàn về như trước. Mở phiếu ở <a href="#/kho-dau/phieu">danh sách phiếu</a>
        → nút thùng rác.</p>
        <p class="muted small">Nếu xoá phiếu nhập mà hàng của nó đã được xuất mất rồi thì hệ
        thống chặn (tồn sẽ âm) — xoá các phiếu sau nó trước.</p>
        <p>Lệch do hao hụt/cân lại thì đừng xoá phiếu — dùng <b>phiếu điều chỉnh</b>, vừa đặt
        đúng tồn vừa giữ lại dấu vết ai chỉnh, chỉnh bao nhiêu.</p>` },
    ],
  },
];
