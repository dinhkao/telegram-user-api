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
        <p>Vào <a href="#/kho-dau/thiet-lap">Thiết lập kho đậu</a>, bấm nút
        <b>Thêm kho</b> / <b>Thêm loại đậu</b> để khai 2 danh mục:</p>
        <ul>
          <li><b>Vị trí kho</b> — Kho A, Kho B… mỗi chỗ chứa đậu là một dòng.</li>
          <li><b>Loại đậu</b> — tên + <b>đơn vị chính</b> (kg, bao, thùng…). Mọi số của loại
            đậu đó về sau đều tính theo đơn vị này.</li>
        </ul>
        <p class="muted small">Thêm mới: ai đăng nhập cũng làm được. Đổi tên/đơn vị: văn phòng.
        Xoá: admin, và chỉ xoá được khi chưa dính phiếu nào.</p>` },
      { title: "Quy đổi đơn vị (bao ↔ kg…)", html: `
        <p>Mỗi loại đậu có <b>một đơn vị chính</b> (khai lúc tạo, vd <i>kg</i>) — <b>mọi số
        tồn kho đều tính theo đơn vị chính</b>. Ngoài ra khai thêm bao nhiêu <b>đơn vị quy đổi</b>
        cũng được: ở <a href="#/kho-dau/thiet-lap">Thiết lập</a> bấm nút <b>⇄</b> ở dòng loại đậu
        rồi nhập <i>1 bao = 50 kg</i>.</p>
        <p>Khi nhập/xuất, mỗi dòng có <b>ô chọn đơn vị</b> (chỉ hiện khi loại đậu đó có khai
        quy đổi). Gõ "2 bao" thì ngay dưới hiện <b>= 100 kg</b> — số vào kho là 100 kg,
        nhưng phiếu vẫn ghi nhớ là bạn đã nhập <i>2 bao</i>.</p>
        <p class="muted small">Xuất cũng so theo đơn vị chính: còn 100 kg mà xuất 3 bao (150 kg)
        thì bị chặn. <b>Sửa tỉ lệ hay xoá đơn vị KHÔNG làm đổi phiếu cũ</b> — phiếu giữ nguyên
        số đã quy đổi lúc nhập, nên tồn quá khứ không tự nhảy.</p>` },
      { title: "Đổi đơn vị chính", html: `
        <p>Trong popup <b>⇄</b> có 2 cách đổi đơn vị chính — chọn đúng cái mình cần:</p>
        <ul>
          <li><b>Đổi TÊN</b> (nút ✏️ ở dòng "Đơn vị chính") — chỉ sửa chữ, vd gõ nhầm "kh" thành
            "kg". <b>Mọi con số giữ nguyên</b>, không quy đổi gì.</li>
          <li><b>★ ở một đơn vị quy đổi</b> — chuyển hẳn sang tính kho theo đơn vị đó, vd đang
            tính theo <i>kg</i> chuyển sang <i>bao</i>. <b>Tồn và mọi phiếu cũ tự chia lại theo
            tỉ lệ</b>: 130 kg thành 2,6 bao — hàng vẫn đúng ngần ấy, chỉ đổi cách đo.</li>
        </ul>
        <p class="muted small">Đơn vị chính cũ tự trở thành một đơn vị quy đổi (1 kg = 0,02 bao)
        nên bấm ★ ở nó là quay về như cũ. Cả hai việc này dành cho <b>văn phòng</b>.</p>` },
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
