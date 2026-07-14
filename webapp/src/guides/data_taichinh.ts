// Hướng dẫn mục TÀI CHÍNH: Két tiền, Sổ quỹ, Bảng giá, Thu tiền/thanh toán.
// Dữ liệu tĩnh — xem guides/types.ts. Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_TAICHINH: Guide[] = [
  {
    key: "ket-tien", icon: "banknote", cat: "Tài chính",
    title: "Két tiền — ai đang giữ tiền",
    desc: "Theo dõi tiền mặt từng đơn: ai giữ, nộp chưa, khách nợ bao nhiêu, trả tiền nhập hàng.",
    routes: ["#/ket"],
    sections: [
      { title: "Két tiền là gì?", html: `
        <p>Trang <a href="#/ket">Két tiền</a> cho biết <b>tiền mặt của từng đơn hàng đang nằm ở đâu</b>:
        ai đang cầm, đã nộp về văn phòng chưa, khách còn nợ bao nhiêu. Mọi thứ <b>tự động</b> —
        bạn cứ làm việc như bình thường (giao hàng, nộp tiền, thu tiền), két tự cập nhật.</p>
        <p class="muted small">Chỉ tính các đơn tạo <b>từ ngày 14/07/2026</b> trở đi. Đơn cũ hơn không hiện ở đây.</p>` },
      { title: "Có những két nào?", html: `
        <ul>
          <li><b>Két của từng người</b> (Trí, Thảo, Trang, Duy…) — tiền mặt người đó đang cầm trong túi/ngăn kéo.</li>
          <li><b>Két văn phòng</b> — tiền mặt shipper đã nộp về, văn phòng <i>chưa</i> làm phiếu thu.</li>
          <li><b>Két ngân hàng</b> — tiền khách chuyển khoản.</li>
          <li><b>Két khách nợ</b> — tiền khách <i>còn thiếu</i> (ký toa hoặc không ký toa). Đây là tiền "trên giấy", chưa cầm được.</li>
          <li><b>Két chưa rõ</b> — đơn được đánh dấu "nộp tiền xong" nhưng <i>không chọn kết quả</i>. Cần xử lý — xem mục dưới.</li>
        </ul>` },
      { title: "Tiền tự chạy thế nào?", html: `
        <p>Mỗi đơn hàng, tiền đi theo đường này:</p>
        <ol>
          <li><b>Giao hàng xong</b> → toàn bộ tiền của đơn vào <b>két người giao</b>.</li>
          <li><b>Nộp tiền</b> (bấm nút Nộp tiền, chọn kết quả):
            <ul>
              <li>💵 <b>Khách trả đủ</b> → tiền chuyển sang <b>Két văn phòng</b>.</li>
              <li>📄 <b>Khách nợ</b> (có/không ký toa) → tiền chuyển sang <b>Két khách nợ</b>.</li>
              <li>🟨 <b>Chiều lấy tiền</b> → tiền <i>vẫn ở két của bạn</i> cho tới khi nộp thật.</li>
            </ul>
          </li>
          <li><b>Văn phòng thu tiền</b> (tạo phiếu thu) → tiền vào <b>két người tạo phiếu thu</b>.
            Thu bằng <b>chuyển khoản</b> → vào <b>Két ngân hàng</b>.</li>
        </ol>
        <p class="muted small">Khách chuyển khoản trước khi giao? Hệ thống tự trừ, người giao chỉ "cầm" phần còn lại.
          Thu một phần cũng được: phần thu đi tiếp, phần thiếu nằm lại két khách nợ.</p>` },
      { title: "Badge ⏰ quá hạn nộp", html: `
        <p>Giao hàng xong phải <b>nộp tiền trước 17:00 cùng ngày</b> (giao sau 17:00 thì hạn là 17:00 hôm sau).
        Ai giữ tiền quá hạn sẽ có badge <span class="cash-badge">⏰ quá hạn nộp</span> ngay trên card két — cả văn phòng đều thấy.</p>` },
      { title: "Chuyển tiền giữa két (văn phòng)", html: `
        <p>Nút <b>Chuyển tiền</b> ở đầu trang Két tiền — dùng khi giao tiền tay: ví dụ cuối ngày Trang kết sổ,
        chuyển tiền từ <i>két Trang</i> về <i>Két văn phòng</i>. Chọn két nguồn → két đích → số tiền → ghi chú.</p>
        <ul>
          <li>Không rút quá số dư đang có của két nguồn.</li>
          <li>Chuyển nhầm? Nhờ <b>admin</b> vào timeline của két bấm <i>xoá</i> lần chuyển đó.</li>
        </ul>` },
      { title: "Trả tiền nhập hàng từ két của mình", html: `
        <p>Khi mua hàng của nhà cung cấp, bạn có thể trả bằng tiền đang cầm: mở <a href="#/nhap-hang">phiếu nhập hàng</a>
        → khối <b>Thanh toán NCC</b> → bấm <b>「Trả từ két của tôi」</b> → nhập số tiền.</p>
        <ul>
          <li>Tiền trừ thẳng vào <b>két của bạn</b>, phiếu nhập ghi lại ai trả, lúc nào, bao nhiêu.</li>
          <li>Trả nhiều lần được. Không trả quá số còn nợ NCC, không trả quá số dư két.</li>
          <li>Danh sách phiếu nhập sẽ thấy <span class="cash-badge ok">✓ đã trả</span> hoặc còn nợ bao nhiêu.</li>
          <li>Trả nhầm? Nhờ <b>admin</b> gỡ lần trả — tiền tự về lại két.</li>
        </ul>` },
      { title: "Két chưa rõ — xử lý sao?", html: `
        <p>Đơn nằm trong <b>Két chưa rõ</b> nghĩa là bước nộp tiền được tick xong mà không chọn kết quả
        (thường do tick tay từ danh sách việc). Cách sửa: mở đơn đó → bấm lại nút <b>Nộp tiền</b> →
        chọn đúng kết quả (trả đủ / nợ). Tiền sẽ tự chạy về đúng két.</p>` },
      { title: "Ai thấy gì? (quyền hạn)", html: `
        <ul>
          <li><b>Nhân viên</b>: chỉ thấy <i>két của mình</i> + trả tiền nhập hàng từ két của mình.</li>
          <li><b>Văn phòng</b> (Trang, Duy): thấy mọi két, tổng khách còn nợ, chuyển tiền giữa két.</li>
          <li><b>Admin</b> (Duy): thêm quyền xoá lần chuyển tiền và gỡ lần trả NCC.</li>
        </ul>` },
      { title: "Mẹo xem nhanh", html: `
        <ul>
          <li>Bấm vào 1 két → <b>timeline</b>: từng dòng tiền vào/ra, chấm tròn bên phải là <b>số dư</b> tại thời điểm đó.</li>
          <li>Trên timeline, bấm tên đơn / phiếu nhập / két đối ứng để nhảy thẳng tới đó.</li>
          <li>Đầu timeline có danh sách <b>đơn có tiền đang nằm trong két</b> — kèm giờ bắt đầu giữ.</li>
          <li>Số liệu cập nhật <b>tự động ngay</b> khi có người giao/nộp/thu — không cần bấm tải lại.</li>
        </ul>` },
    ],
  },
  {
    key: "so-quy", icon: "wallet", cat: "Tài chính",
    title: "Sổ quỹ thu chi",
    desc: "Sổ ghi mọi khoản thu/chi tiền mặt: số dư quỹ, lọc theo loại và theo kỳ.",
    routes: ["#/quy"],
    sections: [
      { title: "Sổ quỹ là gì?", html: `
        <p><a href="#/quy">Sổ quỹ</a> ghi lại <b>mọi khoản thu và chi tiền mặt</b> của cửa hàng.
        Đầu trang hiển thị <b>số dư quỹ thật</b> (toàn sổ) cùng <b>tổng thu / tổng chi trong kỳ</b> bạn đang lọc.</p>
        <p class="muted small">Khác với <a href="#/ket">Két tiền</a>: Két tiền theo dõi <i>tiền của từng đơn đang nằm ở đâu</i>;
        Sổ quỹ là <i>sổ thu–chi tổng</i> của cửa hàng.</p>` },
      { title: "Lọc xem", html: `
        <ul>
          <li>Lọc theo <b>loại</b>: chỉ Thu, chỉ Chi, hoặc cả hai.</li>
          <li>Lọc theo <b>kỳ</b>: hôm nay / 7 ngày / tháng / tự chọn khoảng ngày.</li>
          <li>Danh sách phân trang 20 phiếu, kéo để xem thêm.</li>
        </ul>` },
      { title: "Phiếu tự động vs phiếu tay", html: `
        <ul>
          <li>Khoản <b>thanh toán tiền mặt của đơn</b> tự sinh phiếu trong sổ quỹ, có <b>link tới đơn</b> — không xoá tay được (muốn bỏ thì sửa ở đơn).</li>
          <li>Bạn có thể <b>tạo phiếu thu / chi thủ công</b> cho các khoản khác (tiền lặt vặt, chi phí…).</li>
        </ul>` },
      { title: "Lưu ý", html: `
        <p>Số liệu cập nhật <b>tự động</b> khi có thanh toán mới. Nếu số dư trông lệch, kiểm tra lại kỳ đang lọc
        (tổng thu/chi là <i>trong kỳ</i>, còn số dư là <i>toàn sổ</i>).</p>` },
    ],
  },
  {
    key: "bang-gia", icon: "receipt", cat: "Tài chính",
    title: "Bảng giá",
    desc: "Bảng giá chung + bảng giá riêng từng khách; đơn tự lấy giá theo khách.",
    routes: ["#/bang-gia"],
    sections: [
      { title: "Có mấy loại bảng giá?", html: `
        <ul>
          <li><b>Bảng giá chung</b> (<a href="#/bang-gia">#/bang-gia</a>): các bảng giá dùng chung cho nhiều khách.</li>
          <li><b>Bảng giá riêng của khách</b>: đặt trong trang <a href="#/customers">chi tiết khách</a> — giá riêng cho khách đó.</li>
        </ul>
        <p class="muted small">Khi soạn đơn / hoá đơn, hệ thống <b>tự lấy giá theo khách</b>: ưu tiên giá riêng, rồi tới bảng giá chung.</p>` },
      { title: "Sửa giá", html: `
        <p>Bấm 1 bảng giá → trang chi tiết để <b>sửa giá từng sản phẩm</b>, xem <b>khách nào đang dùng</b> bảng đó,
        và <b>lịch sử đổi giá</b>.</p>` },
      { title: "Giá trong đơn là snapshot", html: `
        <p>Giá của một đơn <b>đã tạo là cố định</b> (chụp lại lúc soạn) — sửa bảng giá về sau <b>không</b> làm đổi giá đơn cũ.
        Muốn đổi giá đơn cũ thì sửa trực tiếp trên <a href="#/orders">đơn</a> đó (khi chưa khoá hoá đơn).</p>` },
      { title: "Đổi mã sản phẩm không ảnh hưởng", html: `
        <p>Bảng giá gắn theo <b>danh tính sản phẩm</b> (không phải theo mã chữ). Đổi mã SP <b>không</b> làm mất giá đã đặt.
        Xem thêm bài <a href="#/huong-dan/san-pham">Sản phẩm</a>.</p>` },
    ],
  },
];
