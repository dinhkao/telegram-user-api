// Hướng dẫn KHO (thùng/sản phẩm/vị trí/cần làm hàng) — dữ liệu tĩnh (xem guides/types.ts). Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_KHO: Guide[] = [
  {
    key: "kho", icon: "box", cat: "Kho & hàng hoá",
    title: "Kho hàng & thùng",
    desc: "Mọi thùng trong kho: số thùng, tồn, xuất cho đơn, chuyển hàng, kiểm kho theo vị trí.",
    routes: ["#/kho", "#/thung", "#/so-thung", "#/kiem-kho", "#/dieu-chinh"],
    sections: [
      { title: "Trang Kho hàng là gì?", html: `
        <p>Trang <a href="#/kho">Kho hàng</a> liệt kê <b>mọi thùng</b> trong kho dạng phẳng —
        mỗi dòng là <b>1 thùng vật lý</b> (1 kiện/hũ) đang có ở đâu đó. Bạn <b>lọc theo mã SP hoặc vị trí</b>
        bằng ô tìm ở trên (gõ <i>mã SP · số thùng · vị trí</i>).</p>
        <p>Trên cùng có mấy nút đi nhanh: <b>Cần làm</b> (<a href="#/nhu-cau">nhu cầu</a>),
        <b>Sản phẩm</b> (<a href="#/san-pham">danh mục SP</a>), <b>Số thùng</b> (<a href="#/so-thung">số gọi</a>),
        <b>Chuyển kho</b>. Bấm chip <b>Ô thùng / Gọn</b> để đổi cách xem.</p>
        <p class="muted small">Lưu ý quan trọng: các tính năng kho chỉ áp dụng cho <b>đơn tạo từ hôm nay trở đi</b>.
          Đơn cũ chưa đi qua luồng kho nên không tính tồn/xuất ở đây.</p>` },
      { title: "Mã thùng = số gọi 001–999", html: `
        <p>Mỗi thùng có một <b>SỐ GỌI 3 chữ số</b> (từ <b>001</b> đến <b>999</b>), dùng chung cho <b>cả kho</b>.
        Ngoài kho mọi người chỉ hô <i>"lấy thùng 347"</i> cho gọn — không cần biết SP gì.</p>
        <ul>
          <li>Số <b>xoay vòng</b>: khi một thùng <b>hết hàng</b>, số của nó được <b>tái dùng</b> cho thùng mới.
            Hết 999 thì quay về 001.</li>
          <li>Vì số tái dùng, <b>số gọi KHÔNG phải danh tính thật</b> của thùng. Danh tính thật là
            <i>id</i> (mã trong link <a href="#/thung">chi tiết thùng</a>) — lịch sử luôn bám theo id.</li>
        </ul>
        <p>Xem toàn bộ số gọi ở <a href="#/so-thung">Số thùng</a>: số nào đang chiếm, số trống, số kế tiếp sẽ cấp.</p>` },
      { title: "Thông tin 1 thùng", html: `
        <p>Bấm vào 1 thùng để mở <a href="#/thung">chi tiết thùng</a>. Mỗi thùng có:</p>
        <ul>
          <li><b>Số lượng</b> (số cây/gói lúc nhập) và <b>Còn lại</b> = số lượng − đã xuất. <i>Tồn</i> chính là phần còn lại.</li>
          <li><b>Ngày SX</b>, <b>Đơn vị</b> chứa (Thùng / Kiện / Hũ…), <b>Vị trí</b> kho (Kho A / Kho B…) để biết để ở đâu.</li>
          <li><b>Nguồn</b> — phiếu sản xuất đã tạo ra thùng này. <b>Ghi chú</b> tự lưu khi rời ô.</li>
        </ul>` },
      { title: "Nhập & xuất thùng", html: `
        <ul>
          <li><b>Nhập thùng mới</b>: làm ở <b>phiếu sản xuất</b> (khối <i>Nhập thùng</i>) — chọn SP, đơn vị, vị trí, số lượng.</li>
          <li><b>Xuất cho đơn</b>: mở <a href="#/orders">chi tiết đơn</a> → khối <b>Xuất kho cho đơn</b> → bấm
            <b>Chọn thùng</b>. Hệ thống <b>không cho vượt số cần</b> của đơn. Xuất đủ mọi mã rồi bấm
            <b>Chốt xuất kho</b> để khoá (chỉ admin mở lại).</li>
          <li>Chọn nhầm? Bấm <b>Thu hồi</b> ở đơn — hàng trả lại thùng (nhớ đảm bảo thùng đó chưa giao khách).</li>
        </ul>` },
      { title: "Chuyển hàng giữa 2 thùng", html: `
        <p>Ở chi tiết thùng, khối <b>Chuyển hàng sang … khác</b>: dời hàng thật sang một thùng khác
        <b>cùng mã SP</b> (ví dụ gom 2 thùng lẻ thành 1, hoặc đổi kệ).</p>
        <ul>
          <li>Chọn nơi nhận → nhập số → bấm <b>Chuyển</b>. Không cho vượt số còn lại.</li>
          <li>Đây là <b>bút toán kép</b>: thùng này giảm, thùng kia tăng — <b>tồn tổng của kho không đổi</b>,
            có lịch sử 2 chiều.</li>
        </ul>` },
      { title: "Vô hiệu & xoá thùng", html: `
        <ul>
          <li><b>Vô hiệu hoá</b> thùng (thùng lỗi/hỏng): thùng bị <i>loại khỏi tồn</i>, không phân bổ cho đơn,
            không tính vào phiếu SX. Có thể <b>Kích hoạt lại thùng</b> sau.</li>
          <li><b>Trả về nguyên liệu</b>: dùng cho thùng nguyên kiện — trả ngược thành nguyên liệu.</li>
          <li><b>Xoá thùng (admin)</b>: chỉ admin, và <b>cấm nếu thùng đã xuất cho đơn</b> — thu hồi trước đã.</li>
        </ul>` },
      { title: "Kiểm kho theo vị trí", html: `
        <p>Kiểm kho làm theo <b>từng vị trí</b>. Vào <a href="#/vi-tri">Vị trí kho</a> → mở 1 vị trí →
        bấm <b>Kiểm kho</b> (hoặc <b>Tiếp tục kiểm kho</b> nếu đang có phiếu nháp). Mở
        <a href="#/kiem-kho">phiếu kiểm kho</a>:</p>
        <ul>
          <li>Phiếu <b>chụp số sổ sách</b> (số hệ thống đang ghi) <i>cố định</i> lúc tạo; bạn nhập
            <b>Thực tế</b> đếm được cho từng thùng, hệ thống tính <b>Lệch</b>.</li>
          <li>Mỗi vị trí chỉ 1 phiếu nháp, và <b>khoá 1 người kiểm</b> — người khác chỉ xem.</li>
          <li>Nếu kho <b>biến động</b> khi bạn đang kiểm (có người xuất/nhập), phiếu báo
            <i>"Kho đã biến động — phiếu không còn chính xác"</i> → bấm
            <b>Cập nhật lại theo tồn hiện tại</b> (giữ số đã đếm) hoặc <b>Huỷ phiếu</b>.</li>
          <li>Đếm xong bấm <b>Hoàn tất</b> để chốt.</li>
          <li>Chốt xong nếu có <b>thùng lệch</b>, văn phòng bấm <b>「⚖ Áp dụng số đếm vào kho」</b> —
            hệ thống tạo <b>phiếu điều chỉnh</b> cho từng thùng lệch (áp theo <i>mức lệch</i>, không đè
            các xuất/nhập hợp lệ sau lúc đếm; áp đúng 1 lần/phiếu; admin gỡ được từng phiếu điều chỉnh).</li>
        </ul>` },
      { title: "Phiếu điều chỉnh tồn thùng", html: `
        <p>Muốn sửa tồn 1 thùng cho đúng thực tế (đếm sót, sổ ghi nhầm…) mà không qua kiểm kho:
        vào <b>chi tiết thùng</b> → khối <b>「Điều chỉnh tồn」</b> (văn phòng) → nhập <b>tồn thực tế</b>
        + <b>lý do bắt buộc</b>.</p>
        <p><b>Phân biệt với Xuất hủy:</b> hàng <b>hư / hết hạn / bỏ đi thật</b> → dùng <b>Xuất hủy</b>
        (bắt buộc chụp ảnh bằng chứng). <b>Điều chỉnh</b> chỉ dành cho <b>sửa số đếm sai</b> —
        app sẽ nhắc khi bạn điều chỉnh giảm.</p>
        <ul>
          <li>Điều chỉnh <b>không sửa số gốc</b> của thùng — mỗi lần là 1 <b>phiếu điều chỉnh</b> có
            lịch sử (ai, lúc nào, lý do, số cũ → mới), hiện ngay trong chi tiết thùng.</li>
          <li><b>Admin gỡ phiếu</b> = hoàn nguyên tồn; bị chặn nếu phần tồn đã tăng đã được dùng
            (gỡ sẽ làm tồn âm).</li>
          <li>Xem <b>mọi phiếu điều chỉnh</b> (kể cả từ kiểm kho) ở dashboard
            <a href="#/dieu-chinh">Điều chỉnh tồn</a> (menu ☰ Thêm → Kho).</li>
        </ul>` },
    ],
  },
  {
    key: "san-pham", icon: "tag", cat: "Kho & hàng hoá",
    title: "Sản phẩm (mã, đơn vị, công thức)",
    desc: "Danh mục sản phẩm: đổi mã tự do, đơn vị đếm, công thức nguyên liệu, cờ mua/bán, link KiotViet.",
    routes: ["#/san-pham"],
    sections: [
      { title: "Danh mục sản phẩm", html: `
        <p><a href="#/san-pham">Sản phẩm</a> là <b>danh mục mọi mã hàng</b>. Bấm một mã để mở
        <a href="#/kho">chi tiết SP</a> (đường dẫn theo mã, ví dụ <i>#/kho/K2L</i>): xem tồn, danh sách thùng,
        đơn có SP này, và mọi cài đặt của SP. Nút <b>Tạo mã</b> ở trên để thêm SP mới.</p>` },
      { title: "Mã SP đổi tự do — không sợ đứt", html: `
        <p>Ô <b>Mã SP</b> ở chi tiết SP đổi được <b>tự do</b> (admin). Yên tâm:</p>
        <ul>
          <li>Danh tính thật của SP là <b>id bất biến</b> — đổi mã <b>KHÔNG làm đứt</b> liên kết, đơn cũ,
            bảng giá hay tồn kho.</li>
          <li><b>Mã cũ vẫn tra được</b>: gõ mã cũ vẫn ra đúng SP, link cũ tự chuyển hướng.</li>
          <li>Không đặt mã <b>toàn chữ số</b> (dễ nhầm với số lượng).</li>
        </ul>` },
      { title: "Đơn vị đếm", html: `
        <p>Ô <b>Đơn vị</b> = đơn vị đếm của SP (cây / gói / kg…). Sửa ở chi tiết SP; số hiển thị đúng
        đơn vị đó ở <b>khắp nơi</b> (kho, đơn, nhu cầu).</p>
        <p class="muted small">Khác với <i>đơn vị chứa</i> của thùng (Thùng/Kiện/Hũ) — cái đó là cách đóng thùng, không phải cách đếm SP.</p>` },
      { title: "Quy đổi đơn vị", html: `
        <p>Khối <b>Quy đổi đơn vị</b> ở chi tiết SP: khai báo SP có <b>nhiều đơn vị</b> với tỉ lệ quy đổi
        về đơn vị gốc — ví dụ đơn vị gốc là <i>cây</i>, thêm <i>1 thùng = 30 cây</i>, <i>1 kiện = 120 cây</i>.</p>
        <ul>
          <li><b>Thêm/sửa tỉ lệ</b>: văn phòng. <b>Xoá đơn vị</b>: admin.</li>
          <li>Tỉ lệ giữa 2 đơn vị bất kỳ tự suy ra từ tỉ lệ về gốc (1 kiện = 4 thùng).</li>
        </ul>` },
      { title: "Công thức / BOM (nguyên liệu)", html: `
        <p>Khối <b>Công thức — nguyên liệu</b> ở chi tiết SP: khai báo 1 SP cần những <b>nguyên liệu</b>
        (là SP khác) theo <b>tỉ lệ</b> (lượng NL cho 1 đơn vị thành phẩm).</p>
        <ul>
          <li>Phiếu <b>đóng gói</b>: <b>bắt buộc</b> có công thức + chọn đủ thùng nguyên liệu — hệ thống trừ kho NL khi nhập.</li>
          <li>Phiếu <b>sản xuất</b>: <b>không cần</b> nguyên liệu.</li>
        </ul>` },
      { title: "Cờ Mua / Bán", html: `
        <p>Khối <b>Mua bán</b> có 2 cờ (admin):</p>
        <ul>
          <li><b>Có thể bán / Không bán</b> — tắt thì SP <i>biến khỏi gợi ý</i> khi tạo hoá đơn bán.</li>
          <li><b>Có thể nhập / Không nhập</b> — tắt thì SP <i>biến khỏi gợi ý</i> khi tạo phiếu nhập hàng.</li>
        </ul>
        <p class="muted small">Gõ tay mã vẫn nhận được — cờ chỉ ẩn khỏi <b>gợi ý</b> tự động.</p>` },
      { title: "Liên kết KiotViet & xoá SP", html: `
        <ul>
          <li>Chi tiết SP có khối <b>KiotViet</b>: <b>Liên kết</b> với SP có sẵn, hoặc <b>Tạo trên KiotViet</b>
            nếu chưa có. SP chưa liên kết hiện cảnh báo ⚠️.</li>
          <li><b>Xoá SP</b>: chỉ admin.</li>
        </ul>` },
    ],
  },
  {
    key: "vi-tri", icon: "box", cat: "Kho & hàng hoá",
    title: "Vị trí kho",
    desc: "Khai báo các vị trí (Kho A, Kho B…), gắn thùng vào vị trí, kiểm kho theo từng vị trí.",
    routes: ["#/vi-tri"],
    sections: [
      { title: "Vị trí kho là gì?", html: `
        <p><a href="#/vi-tri">Vị trí kho</a> là danh sách các <b>nơi cất hàng</b> (Kho A, Kho B, kệ…).
        Mỗi thùng được <b>gắn vị trí</b> để biết đang để ở đâu. Bấm một vị trí → mở
        <a href="#/vi-tri">chi tiết vị trí</a> xem các thùng đang nằm ở đó.</p>` },
      { title: "Tự tạo & sửa vị trí", html: `
        <ul>
          <li>Vị trí do <b>người dùng tự định nghĩa</b>: gõ tên vào ô <i>"Tên vị trí mới (vd Kho C)"</i> để thêm.</li>
          <li>Sửa được <b>tên</b> và <b>ghi chú</b>. <b>Xoá</b> vị trí = chỉ admin.</li>
          <li>Mỗi vị trí có <b>ảnh / trao đổi / lịch sử</b> riêng — card ở danh sách hiện <b>thumbnail ảnh mới nhất</b>.</li>
        </ul>` },
      { title: "Gắn thùng vào vị trí", html: `
        <p>Gán vị trí cho thùng ở <a href="#/thung">chi tiết thùng</a> (ô <b>Vị trí</b>), hoặc lúc
        <b>nhập thùng</b> ở phiếu sản xuất. Thùng chưa gán nằm trong nhóm <i>"Chưa xếp vị trí"</i>.</p>` },
      { title: "Kiểm kho theo vị trí", html: `
        <p>Việc <b>kiểm kho</b> luôn làm theo <b>từng vị trí</b>. Ở chi tiết vị trí bấm <b>Kiểm kho</b>
        để tạo phiếu đếm cho riêng vị trí đó (xem bài <a href="#/huong-dan/kho">Kho hàng &amp; thùng</a>).</p>` },
    ],
  },
  {
    key: "nhu-cau", icon: "chart", cat: "Kho & hàng hoá",
    title: "Cần làm hàng (nhu cầu)",
    desc: "Tính hàng cần sản xuất/đóng gói để đủ đơn đang chờ, kèm phân loại đủ làm / thiếu NL / kẹt.",
    routes: ["#/nhu-cau"],
    sections: [
      { title: "Trang Cần làm hàng", html: `
        <p><a href="#/nhu-cau">Cần làm hàng</a> tính <b>cần làm bao nhiêu hàng</b> để đủ cho các đơn
        <b>đang chờ, chưa xuất kho</b>. Nó gộp nhu cầu mọi đơn theo mã SP rồi so với tồn hiện có,
        cho bạn biết cần <b>sản xuất / đóng gói</b> thêm bao nhiêu.</p>
        <p class="muted small">Chỉ tính <b>đơn tạo từ hôm nay trở đi</b> (đơn cũ chưa qua luồng kho).
          Đổi cách xem bằng thanh trượt <b>Chi tiết / Gọn / Sơ đồ</b>.</p>` },
      { title: "Đọc kết quả", html: `
        <ul>
          <li>Nếu đủ hết: hiện <b>"Kho đủ cho mọi đơn đang chờ"</b>.</li>
          <li>Nếu thiếu: chia 2 khu — <b>CẦN QUYẾT ĐỊNH</b> (phải làm/mua nguyên liệu trước, hoặc cấu hình cách SX)
            và <b>LÀM ĐƯỢC</b> (sẵn sàng — SX trực tiếp hoặc đóng gói).</li>
          <li>Mỗi mã hiện <b>thiếu bao nhiêu</b>, tồn / cần / số đơn liên quan, và ước lượng số mâm.</li>
        </ul>` },
      { title: "Phân loại tình trạng", html: `
        <p>Mỗi mã có một dòng <b>phán</b> tuỳ theo công thức và tồn kho:</p>
        <ul>
          <li><b>Làm được</b> — sản xuất trực tiếp hoặc đóng gói từ NL đủ hàng.</li>
          <li><b>Thiếu nguyên liệu</b> — đóng gói được nhưng chưa đủ NL → cần làm/mua NL trước
            (bấm <i>Xem nguyên liệu</i>).</li>
          <li><b>Chưa cấu hình cách SX</b> — SP chưa bật cách sản xuất → cần <i>Bật SX trực tiếp</i> hoặc thêm công thức.</li>
          <li><b>Kẹt</b> — không có đường nào làm ra được cho tới khi xử lý NL/cấu hình.</li>
        </ul>
        <p class="muted small">Nếu có đơn chưa nhập sản phẩm, trang cảnh báo <i>"kết quả có thể KHÔNG chính xác"</i> — nhập SP cho đơn đó rồi xem lại.</p>` },
    ],
  },
];
