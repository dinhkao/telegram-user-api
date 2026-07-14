// Hướng dẫn ĐƠN HÀNG (xem/xử lý, tạo, hoá đơn) — dữ liệu tĩnh (xem guides/types.ts).
// Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_DON: Guide[] = [
  {
    key: "don-hang", icon: "clipboard", cat: "Đơn hàng & khách",
    title: "Đơn hàng — xem & xử lý đơn",
    desc: "Danh sách đơn, các bước soạn–giao–nộp–nhận, ảnh, hoá đơn, timeline.",
    routes: ["#/orders", "#/order", "#/dang-giao"],
    sections: [
      { title: "Trang Đơn dùng để làm gì?", html: `
        <p>Trang <a href="#/orders">Đơn</a> là bảng điều khiển chính: mọi đơn hàng nằm ở đây,
        mới nhất lên trên. Mỗi đơn là 1 thẻ (card) — bấm vào để mở <b>chi tiết đơn</b> và làm việc.</p>
        <p>Card hiện tên khách, sản phẩm, tổng tiền, trạng thái và <b>ảnh mới nhất</b> của đơn ở bên trái.
        Mọi thay đổi (ai đó giao, nộp, thu tiền, thêm ảnh, bình luận…) <b>tự cập nhật ngay</b> —
        không cần bấm tải lại.</p>` },
      { title: "4 kiểu xem + tìm & lọc", html: `
        <p>Góc trên có thanh đổi <b>kiểu xem</b> — bấm để đổi, hệ thống nhớ lựa chọn của bạn:</p>
        <ul>
          <li><b>☰ Chi tiết</b> — đầy đủ nhất (sản phẩm, tiền, ảnh).</li>
          <li><b>≣ Gọn</b> — thẻ ngắn hơn.</li>
          <li><b>▬ Siêu gọn</b> — 1 dòng/đơn (5 icon trạng thái + 1 dòng chữ), lướt nhanh.</li>
          <li><b>📅 Lịch giao</b> — mở <a href="#/lich">lịch giao</a> theo ngày.</li>
        </ul>
        <p>Ô tìm kiếm: gõ <b>tên khách hoặc sản phẩm</b> (không cần dấu). Dưới đó là các <b>ô lọc</b> kèm số đếm:
        <b>Chưa soạn · Chưa giao · Chưa nộp · Chưa nhận · Còn nợ</b> (và Đã xong / Chưa xong).
        Bấm ô lọc để chỉ xem nhóm đó.</p>
        <p class="muted small">Danh sách tải 20 đơn/lần, cứ kéo xuống là tự tải thêm tới khi hết ("— Hết đơn —").</p>` },
      { title: "Các BƯỚC của một đơn", html: `
        <p>Mỗi đơn đi theo một chuỗi bước, tick lần lượt trong khối <b>Tiến độ</b> ở chi tiết đơn
        (hoặc từ danh sách <a href="#/viec">Việc</a>):</p>
        <ol>
          <li><b>Bán HĐ</b> — lên hoá đơn.</li>
          <li><b>Soạn</b> (soạn hàng).</li>
          <li><b>Giao</b> (giao hàng).</li>
          <li><b>Nộp</b> (nộp tiền về).</li>
          <li><b>Nhận</b> (văn phòng nhận / thu tiền).</li>
        </ol>
        <p>Ngoài ra có <b>in hoá đơn giao</b>. Icon thứ 6 cho biết tiền: 💰 đã có thu ·
        😡 còn nợ (đang theo dõi) · 😑 đã bỏ theo dõi nợ.</p>` },
      { title: "Quy tắc chốt bước (quan trọng)", html: `
        <p>Mặc định hệ thống <b>khoá bước theo thứ tự</b> để không bỏ sót:</p>
        <ul>
          <li><b>Soạn hàng</b> chỉ được đánh dấu xong khi đơn <b>đã chốt xuất kho</b>
            (bấm <b>「Xuất kho」</b> → chọn đủ thùng → chốt) <b>và có ảnh soạn hàng</b>.</li>
          <li>Chốt xuất kho xong sẽ <b>khoá phân bổ kho</b> (không lấy/trả thùng nữa) — trừ admin.</li>
          <li><b>Giao hàng</b> cần <b>soạn xong</b> trước.</li>
          <li><b>In hoá đơn giao</b> cần <b>giao xong</b> trước.</li>
        </ul>
        <p class="muted small">Nếu bấm mà bị chặn, hệ thống báo lý do (thiếu ảnh, chưa chốt xuất kho…). Cứ làm nốt bước còn thiếu.</p>` },
      { title: "Trong chi tiết đơn có gì?", html: `
        <p>Mở 1 đơn, khối <b>Thao tác nhanh</b> có sẵn các nút:</p>
        <ul>
          <li><b>Hoá đơn</b> — xem/sửa hoá đơn (mở trang riêng <a href="#/order">sửa hoá đơn</a>) hoặc tạo HĐ KiotViet.</li>
          <li><b>Thanh toán</b> — nộp / thu tiền của đơn.</li>
          <li><b>Xuất kho</b> — chọn thùng xuất cho đơn rồi chốt.</li>
          <li><b>Chụp ảnh / Ảnh</b> — chụp bằng camera trong app hoặc chọn từ máy; ảnh <b>đồng bộ 2 chiều</b>
            với topic Telegram của đơn (ảnh đăng trong topic tự về đây, ảnh bạn thêm ở đây tự sang topic).</li>
          <li><b>In hoá đơn</b> — in phiếu giao.</li>
          <li><b>Trao đổi</b> — bình luận nội bộ trên đơn.</li>
          <li><b>Tiến độ</b> — tick các bước soạn/giao/nộp/nhận.</li>
        </ul>
        <p>Cuối đơn có <b>Lịch sử thao tác</b> (ai làm gì, lúc nào) và nút <b>Timeline biến động đơn</b>
        (<a href="#/order">#/order/:id/timeline</a>) — xem cả đời đơn kèm rail <b>tiền còn phải thu</b>.</p>` },
      { title: "Xoá ảnh, đổi khách, xoá đơn", html: `
        <ul>
          <li><b>Xoá ảnh = xoá mềm</b>: ảnh vẫn hiện nhưng có <b>dấu X đỏ</b> gạch chéo — để đối chiếu sau, không mất hẳn.</li>
          <li><b>Đổi khách</b>: nút <b>「Đổi」</b> cạnh tên khách. Nếu đơn <b>đã có HĐ KiotViet</b> thì khoá — không đổi khách được.</li>
          <li><b>Xoá đơn</b> (chỉ <b>admin</b>): bị <b>cấm</b> nếu đơn còn <b>HĐ KiotViet</b> hoặc còn <b>phân bổ kho</b>.
            Xoá HĐ / thu hồi kho trước rồi mới xoá được đơn.</li>
        </ul>` },
      { title: "Trang Đang giao", html: `
        <p>Trang <a href="#/dang-giao">Đang giao</a> ("Đang ở ngoài đường") gom các đơn <b>đã giao nhưng chưa nộp tiền</b>,
        <b>nhóm theo người đang giao</b> — để biết ai đang cầm hàng/tiền của đơn nào.</p>
        <p class="muted small">Không tính đơn hẹn "Chiều lấy tiền". Bấm 1 card để mở đơn đó.</p>` },
    ],
  },

  {
    key: "tao-don", icon: "plus", cat: "Đơn hàng & khách",
    title: "Tạo đơn hàng",
    desc: "2 cách tạo: gõ nhanh bằng text, hoặc soạn từng mặt hàng theo bảng giá khách.",
    routes: ["#/create"],
    sections: [
      { title: "Tạo đơn — 2 cách", html: `
        <p>Trang <a href="#/create">Tạo đơn</a> có 2 tab:</p>
        <ul>
          <li><b>⚡ Nhanh</b> — <b>gõ text đơn</b> tự do (giống nhắn tin đặt hàng), hệ thống tự đọc ra khách + sản phẩm.</li>
          <li><b>📋 Nâng cao</b> — chọn <b>khách trước</b>, rồi soạn <b>từng mặt hàng</b>, giá lấy theo bảng giá của khách.</li>
        </ul>
        <p class="muted small">Tab Nhanh nhanh nhất cho đơn quen tay; tab Nâng cao chắc chắn hơn khi cần kiểm giá từng dòng.</p>` },
      { title: "Cách 1 — ⚡ Nhanh (gõ text)", html: `
        <ol>
          <li>Gõ đơn vào ô lớn: dòng đầu tên/mã khách, mỗi dòng sau 1 mặt hàng (mã · số lượng · giá…).</li>
          <li>Bên dưới hiện <b>👁️ Xem trước</b> ngay khi gõ: <b>nhận diện khách</b> (kèm % khớp và <b>nợ</b> hiện tại),
            bảng hoá đơn và <b>Tổng cộng</b>.</li>
          <li>Khớp đúng khách thì bấm <b>「Tạo đơn」</b>.</li>
        </ol>
        <p>Không cần chọn khách — hệ thống <b>tự nhận từ text</b>. Muốn chắc, có thể chọn tay ở ô "Khách hàng (tùy chọn)".
        Chưa ra khách thì xem "Cách nhận diện" để gõ đúng tên/mã.</p>
        <p class="muted small">Đang gõ dở? Nội dung được giữ lại — rời trang rồi quay lại vẫn còn.</p>` },
      { title: "Cách 2 — 📋 Nâng cao (theo bảng giá)", html: `
        <ol>
          <li><b>① Khách hàng</b>: bấm <b>「Chọn khách hàng」</b>. Chọn xong thấy <b>nợ</b> và <b>bảng giá</b> đang áp
            (Giá chung hoặc bảng giá riêng của khách) — có nút <b>「Xem giá」</b>.</li>
          <li><b>② Sản phẩm & hoá đơn</b>: thêm từng mặt hàng; <b>giá tự gợi ý theo bảng giá</b> của khách ở bước ①.</li>
          <li>Bấm <b>「Lưu & tạo đơn」</b>.</li>
        </ol>
        <p class="muted small">Chưa chọn khách thì bước ② bị khoá ("Chọn khách hàng ở bước 1 trước").</p>` },
      { title: "Sau khi bấm Tạo đơn", html: `
        <p>Hệ thống <b>đăng text đơn vào kênh #don_hang</b> như tài khoản người dùng, rồi <b>tự tạo topic + đơn thật</b>
        và <b>nhảy thẳng vào đơn vừa tạo</b> để bạn làm tiếp (soạn, xuất kho, giao…).</p>
        <p class="muted small">Đây là đơn thật y như đặt qua Telegram — không phải bản nháp.</p>` },
      { title: "Lưu ý & bẫy thường gặp", html: `
        <ul>
          <li>Ở tab Nhanh, nếu tên khách trong text <b>khác</b> khách bạn đang định, phần xem trước sẽ <b>cảnh báo đổi khách</b> — đọc kỹ trước khi tạo.</li>
          <li>Trên điện thoại, khi gõ màn hình <b>chia đôi</b> (ô gõ trên, xem trước dưới) để vừa gõ vừa soi.</li>
          <li>Giá và tổng ở xem trước là <b>tạm tính theo bảng giá hiện tại</b> — kiểm lại số tiền trước khi tạo.</li>
        </ul>` },
    ],
  },

  {
    key: "hoa-don", icon: "receipt", cat: "Đơn hàng & khách",
    title: "Hoá đơn KiotViet (tạo & sửa)",
    desc: "Sửa sản phẩm/giá/khách của đơn, tạo hoá đơn KiotViet, quy tắc khoá sửa.",
    routes: ["#/order"],
    sections: [
      { title: "Trang sửa hoá đơn", html: `
        <p>Từ chi tiết đơn, khối Hoá đơn → mở <b>trang sửa hoá đơn riêng</b> (<a href="#/order">#/order/:id/hoa-don</a>).
        Ở đây bạn chỉnh <b>sản phẩm, số lượng, giá</b> và có thể <b>đổi khách</b> của đơn, rồi <b>tạo hoá đơn KiotViet</b>.</p>
        <p>Trang có 2 tab như trang tạo đơn: <b>⚡ Nhanh</b> và <b>📋 Nâng cao</b>.</p>` },
      { title: "⚡ Nhanh — sửa bằng text", html: `
        <p>Sửa thẳng <b>text đơn</b>, bên dưới có <b>👁️ Xem trước</b> để soi lại, rồi bấm <b>「Lưu」</b>
        (lưu qua đường <i>sửa & nhận diện lại sản phẩm</i>).</p>
        <ul>
          <li>Lưu tab Nhanh = <b>phân tích lại SẢN PHẨM</b> từ text.</li>
          <li><b>Khách giữ nguyên</b> theo ô khách phía trên (muốn đổi thì bấm <b>「Đổi」</b>). Nếu sửa text mà làm đổi khách, hệ thống <b>cảnh báo</b> trước khi lưu.</li>
        </ul>` },
      { title: "📋 Nâng cao — sửa từng dòng", html: `
        <ol>
          <li><b>① Khách hàng</b> (thanh dùng chung phía trên): thấy <b>nợ KiotViet</b> + <b>bảng giá</b> đang áp;
            đổi khách bằng nút <b>「Đổi」</b>.</li>
          <li><b>② Hoá đơn</b>: sửa từng dòng sản phẩm/số lượng/giá; giá <b>lấy theo bảng giá khách ở bước ①</b>.</li>
        </ol>
        <p><b>Đổi khách</b> ở bước ① → trình sửa <b>xoá giá cũ và tra lại giá</b> theo bảng giá của khách mới.
        Có thể thêm <b>VAT / phụ thu (PVC)</b>. Xong bấm <b>「Lưu」</b>.</p>
        <p class="muted small">Bản Nâng cao còn cho chọn 1 ảnh của đơn để đối chiếu khi soạn.</p>` },
      { title: "Khi nào bị KHOÁ sửa?", html: `
        <ul>
          <li><b>Đã có hoá đơn KiotViet</b> → khoá toàn bộ. Muốn sửa lại phải <b>xoá HĐ</b> ở chi tiết đơn trước
            (chỉ <b>admin</b> xoá được HĐ KiotViet).</li>
          <li><b>Đã chốt xuất kho</b> → chỉ sửa được <b>đơn giá, chiết khấu, phụ thu (PVC)</b>;
            <b>sản phẩm, số lượng, VAT giữ nguyên</b>.</li>
          <li><b>Người khác đang sửa</b> đơn này → khoá tạm, chờ họ xong (hệ thống tự mở lại).</li>
        </ul>
        <p class="cash-badge">Bị khoá thì nút mờ đi và có dòng báo lý do — cứ làm theo hướng dẫn trên màn hình.</p>` },
      { title: "Công nợ & giá vốn", html: `
        <ul>
          <li><b>Công nợ khách luôn lấy từ KiotViet</b> — hệ thống <b>không tự tính</b>. Số nợ có thể <b>trễ vài giây</b>
            sau khi tạo HĐ / thu tiền rồi <b>tự đồng bộ lại</b>.</li>
          <li><b>Giá bán và giá vốn của đơn là snapshot vĩnh viễn</b>: đã chốt trên đơn thì không đổi theo bảng giá sau này.
            (Đổi khách/soạn lại thì mới tra giá mới.)</li>
        </ul>` },
    ],
  },
];
