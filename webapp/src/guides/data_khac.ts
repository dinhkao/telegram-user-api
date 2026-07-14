// Hướng dẫn KHÁC & HỆ THỐNG (camera/lịch sử/tài khoản/nút trợ giúp) — dữ liệu tĩnh (xem guides/types.ts). Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_KHAC: Guide[] = [
  {
    key: "camera", icon: "camera", cat: "Khác & hệ thống",
    title: "Camera 2026 (ảnh giám sát)",
    desc: "Thư viện ảnh camera 2 kênh song song, tự làm mới, tải thêm ảnh cũ khi cuộn.",
    routes: ["#/camera"],
    sections: [
      { title: "Trang Camera là gì?", html: `
        <p>Trang <a href="#/camera">Camera</a> là <b>thư viện ảnh chụp từ camera giám sát</b> ở xưởng/kho.
        Ảnh được lưu trên mạng (Cloudinary) và trải theo dòng thời gian — mới nhất ở trên.</p>
        <p class="muted small">Trang này <b>chỉ dành cho văn phòng</b>. Nhân viên không thấy mục Camera trong menu ☰ Thêm.</p>` },
      { title: "Layout 2 cột song song", html: `
        <p>Mặc định màn chia <b>2 cột song song</b>: mỗi <b>hàng là 1 thời điểm</b>, camera
        <b>kênh 11 bên trái</b> ⟷ <b>kênh 14 bên phải</b>. Hai ảnh cùng hàng là 2 camera chụp
        <i>gần như cùng lúc</i> (lệch nhau tối đa 5 giây) nên bạn nhìn được cả 2 góc của một khoảnh khắc.</p>
        <p>Muốn xem kỹ 1 camera? <b>Lọc 1 kênh</b> → màn chuyển sang <b>lưới 3 cột</b> chỉ ảnh của kênh đó.</p>` },
      { title: "Xem và tải thêm ảnh", html: `
        <ul>
          <li><b>Bấm vào ảnh</b> để xem lớn — trong đó có nút <b>phóng to/thu nhỏ</b> và <b>tải ảnh gốc</b>, vuốt qua lại để xem ảnh kế bên.</li>
          <li>Trang <b>tự làm mới ~10 giây một lần</b> — có ảnh mới sẽ tự hiện lên đầu, không cần tải lại.</li>
          <li>Cuộn xuống hết, bấm nút <b>「Xem ảnh cũ hơn」</b> để tải thêm ảnh của các thời điểm trước.</li>
          <li>Muốn xem một khoảng thời gian cụ thể? Dùng <b>bộ lọc thời gian</b> (biểu tượng đồng hồ) ở đầu trang.</li>
        </ul>
        <p class="muted small">Ảnh tải theo nhu cầu (khi bạn cuộn tới) nên trang mở nhanh, không kéo hết cùng lúc.</p>` },
    ],
  },
  {
    key: "lich-su", icon: "history", cat: "Khác & hệ thống",
    title: "Lịch sử thao tác",
    desc: "Nhật ký mọi thao tác toàn app — ai làm gì, lúc nào, có link nhảy thẳng tới thực thể.",
    routes: ["#/lich-su"],
    sections: [
      { title: "Lịch sử thao tác là gì?", html: `
        <p>Trang <a href="#/lich-su">Lịch sử thao tác</a> là <b>nhật ký của MỌI thao tác trong app</b>:
        ai tạo đơn, ai sửa hoá đơn, ai nhập kho, ai thu tiền, ai chuyển két… kèm <b>thời điểm</b> chính xác.</p>
        <p>Dùng khi cần tra "việc này ai làm, lúc mấy giờ", hoặc rà lại một thay đổi bất thường.</p>` },
      { title: "Bấm để nhảy tới thực thể", html: `
        <p>Mỗi dòng lịch sử có <b>LINK tới thực thể được nhắc</b> trong dòng đó — đơn hàng, thùng,
        sản phẩm, khách, phiếu nhập/trả/xuất huỷ… <b>Bấm vào link</b> để nhảy thẳng tới trang chi tiết
        của thứ đó thay vì phải đi tìm.</p>` },
      { title: "Timeline riêng của từng đơn", html: `
        <p>Ngoài lịch sử toàn app, <b>mỗi đơn hàng còn có timeline riêng</b> — nút Timeline ở trang chi tiết đơn
        (đường dẫn dạng <span class="muted small">#/order/&lt;mã&gt;/timeline</span>). Nó kể <b>cả đời của đơn</b>:
        tạo đơn → xuất hoá đơn KiotViet → xuất kho → soạn/giao/nộp/nhận → từng lần thu tiền, kèm rail
        <b>tiền còn phải thu</b> chạy dọc theo thời gian.</p>` },
      { title: "Timeline của thùng và két", html: `
        <ul>
          <li><b>Thùng kho</b> có timeline biến động <b>tồn</b>: nhập vào, xuất cho đơn nào, chuyển hàng, xuất huỷ.</li>
          <li><b>Két tiền</b> có timeline biến động <b>số dư</b>: từng dòng tiền vào/ra, chấm bên phải là số dư tại thời điểm đó (xem thêm bài <a href="#/huong-dan/ket-tien">Két tiền</a>).</li>
        </ul>` },
    ],
  },
  {
    key: "tai-khoan", icon: "lock", cat: "Khác & hệ thống",
    title: "Tài khoản, quyền & cài đặt",
    desc: "Đăng nhập bằng PIN, 3 mức quyền, đăng xuất, quản lý user và thống kê sử dụng.",
    routes: ["#/users", "#/usage"],
    sections: [
      { title: "Đăng nhập", html: `
        <p>Mỗi người có một <b>tên đăng nhập</b> và một <b>mã PIN</b> riêng. Nhập đúng cả hai để vào app.
        PIN là bí mật cá nhân — không đưa cho người khác.</p>` },
      { title: "3 mức quyền", html: `
        <ul>
          <li><b>NHÂN VIÊN</b> — làm việc thường ngày, chỉ thấy phần liên quan tới mình (ví dụ chỉ két của mình).</li>
          <li><b>VĂN PHÒNG</b> — thêm quyền <b>nhận tiền, tạo phiếu thu, chuyển tiền giữa két, tạo hoá đơn KiotViet, thu tiền hàng loạt</b> và xem toàn cảnh.</li>
          <li><b>ADMIN</b> — quyền cao nhất, thêm quyền <b>XOÁ</b>: xoá đơn, xoá thùng, xoá sản phẩm, xoá hoá đơn KiotViet, xoá lần chuyển tiền/lần trả nhà cung cấp…</li>
        </ul>
        <p class="muted small">Nút nào bạn không có quyền dùng sẽ mờ đi và báo lý do khi bấm.</p>` },
      { title: "Trang Cài đặt & đăng xuất", html: `
        <p>Bấm biểu tượng <b>⚙️ (bánh răng) trên cùng</b> để mở trang Cài đặt: xem mình đang đăng nhập bằng
        tài khoản nào, và <b>Đăng xuất</b> khi cần. Trang này cũng có nút cập nhật ứng dụng.</p>
        <p class="muted small">Admin còn thấy thêm vài công tắc quy trình hệ thống ở ngay trang này.</p>` },
      { title: "Quản lý user (admin)", html: `
        <p>Admin vào <a href="#/users">Quản lý user</a> (trong menu ☰ Thêm) để <b>tạo tài khoản mới,
        đổi tên hiển thị, đổi quyền, đặt lại PIN</b> cho từng người.</p>` },
      { title: "Thống kê sử dụng (admin)", html: `
        <p>Admin vào <a href="#/usage">Thống kê sử dụng</a> để xem <b>ai đang dùng tính năng nào, bao nhiêu lần</b>.
        Chọn khoảng <b>7 / 30 / 90 ngày</b> và lọc theo từng người; xem trang được dùng nhiều nhất, nút bấm nhiều/ít nhất.
        Hữu ích để biết ai chưa quen tính năng mới.</p>
        <p class="muted small">Chỉ đếm gộp theo ngày/người/trang — không ghi lại từng cú bấm chi tiết.</p>` },
    ],
  },
  {
    key: "nut-tro-giup", icon: "info", cat: "Khác & hệ thống",
    title: "Nút ? trợ giúp & hướng dẫn",
    desc: "Nút tròn dấu ? nổi mọi trang: mở hướng dẫn, ưu tiên bài đúng trang, kéo được.",
    routes: [],
    sections: [
      { title: "Nút ? ở đâu?", html: `
        <p>Có một <b>nút tròn với dấu "?"</b> nổi trên màn hình ở <b>mọi trang</b> của app. Đây là lối tắt
        mở kho <a href="#/huong-dan">Hướng dẫn sử dụng</a> — bạn không cần đi tìm menu.</p>` },
      { title: "Tự đẩy bài đúng trang lên đầu", html: `
        <p>Khi bạn bấm nút "?", trang Hướng dẫn <b>tự đẩy các bài LIÊN QUAN TRANG bạn đang xem lên đầu</b>
        (nhóm <b>"Trang bạn đang xem"</b>). Ví dụ đang ở trang Két tiền mà bấm "?", bài <i>Két tiền</i>
        hiện ngay trên cùng — không phải cuộn tìm.</p>` },
      { title: "Kéo được để đổi chỗ", html: `
        <p>Nút <b>kéo được</b>: chạm giữ rồi rê tới góc khác nếu nó che mất thứ bạn cần bấm. App
        <b>nhớ vị trí</b> bạn đặt cho lần sau. Bấm nhanh (không rê) thì mở Hướng dẫn như thường.</p>` },
      { title: "Thỉnh thoảng nút nhún nhẹ", html: `
        <p>Thỉnh thoảng nút <b>nhún nhẹ</b> để nhắc bạn nhớ là có trợ giúp ở đây — không phải lỗi.</p>` },
      { title: "Hướng dẫn do AI viết", html: `
        <p>Toàn bộ các bài hướng dẫn trong app <b>do AI viết</b>. Đã cố gắng cho sát thực tế, nhưng
        <b>nếu có chỗ chưa rõ hoặc chưa đúng, cứ hỏi Duy</b>.</p>` },
    ],
  },
];
