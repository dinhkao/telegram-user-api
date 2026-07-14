// Hướng dẫn KHÁCH HÀNG & thu tiền/trả hàng/việc/lịch giao — dữ liệu tĩnh (xem guides/types.ts). Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_KHACH: Guide[] = [
  {
    key: "khach-hang", icon: "user", cat: "Đơn hàng & khách",
    title: "Khách hàng & công nợ",
    desc: "Danh sách khách, xem công nợ, bảng giá riêng, dòng thời gian đơn + thanh toán.",
    routes: ["#/customers", "#/khach"],
    sections: [
      { title: "Tìm và mở khách", html: `
        <p>Trang <a href="#/customers">Khách hàng</a> liệt kê toàn bộ khách. Gõ vào ô tìm để lọc —
        <b>không cần dấu</b> (gõ "trang" ra "Trang", "hue" ra "Huệ"). Bấm vào một khách để mở
        <b>chi tiết khách</b> (<a href="#/khach">#/khach/…</a>).</p>
        <p class="muted small">Chi tiết khách có: công nợ, bảng giá riêng, dòng thời gian đơn/thanh toán, ảnh & trao đổi, lịch sử.</p>` },
      { title: "Công nợ lấy từ KiotViet", html: `
        <p>Số <b>công nợ</b> của khách <b>luôn lấy thẳng từ KiotViet</b> — hệ thống <i>không</i> tự tính lại.
        Đây là con số chuẩn để đối chiếu. Nếu vừa tạo hoá đơn mà nợ chưa đổi, chờ vài giây rồi mở lại
        (KiotViet cập nhật hơi trễ, hệ thống tự lấy lại sau).</p>` },
      { title: "Bảng giá riêng của khách", html: `
        <p>Trong chi tiết khách, khối <b>Giá bán</b> có <b>Giá riêng của khách (ĐÈ lên bảng giá chung)</b>:
        giá bán từng mặt hàng dành riêng cho khách đó. Khi tạo đơn cho khách, đơn <b>tự lấy giá này</b> — khỏi gõ giá lại.</p>
        <ul>
          <li>Bấm <b>Thêm SP</b> để thêm mã + giá, rồi <b>Lưu giá riêng</b>.</li>
          <li>Có thể gắn thêm một <b>Bảng giá chung</b>; giá riêng luôn <b>đè lên</b> giá chung.</li>
          <li>Mặt hàng không có giá riêng → dùng giá chung/mặc định; thêm vào bảng riêng lúc nào cũng được.</li>
          <li>Đổi khách của một đơn (ở trang sửa hoá đơn) → giá tra lại theo bảng giá của khách mới.</li>
        </ul>` },
      { title: "Dòng thời gian & rail nợ", html: `
        <p>Trong chi tiết khách có <b>dòng thời gian</b> (feed) ghép <b>đơn hàng</b> và <b>lần thanh toán</b>
        vào một mạch, có <b>dây nối</b> lần thu với đơn nó trả. Bên cạnh là <b>rail nợ</b> — số nợ
        <i>còn lại sau mỗi sự kiện</i>.</p>
        <ul>
          <li>Số nợ sau mỗi mốc là số <b>tính lại có kiểm chứng</b>, chỉ hiện khi đoạn đó <b>cân khớp</b>.</li>
          <li>Nếu chỉ ước lượng được, số hiện kèm dấu <b>≈</b>; đoạn không cân thì để trống.</li>
        </ul>` },
      { title: "Lịch của khách", html: `
        <p>Nút mở <b>lịch khách</b> (<a href="#/khach">#/khach/…/lich</a>): xem đơn và thanh toán của khách
        <b>theo từng ngày</b>. Lịch cuộn liền mạch — vuốt lên/xuống qua các tháng, có nút <b>Hôm nay</b>.</p>` },
      { title: "Trả hàng & sửa thông tin", html: `
        <p>Trong chi tiết khách có nút <b>↩ Trả hàng</b> — mở ngay hộp thoại tạo <b>phiếu trả hàng</b> cho
        khách này (xem bài <a href="#/huong-dan/tra-hang">Trả hàng</a>).</p>
        <p>Bạn cũng <b>sửa được thông tin khách</b> (tên, SĐT, địa chỉ, ghi chú) và đính kèm <b>ảnh / trao đổi</b>;
        mọi thay đổi vào <b>lịch sử</b> của khách.</p>` },
    ],
  },
  {
    key: "thu-tien", icon: "banknote", cat: "Đơn hàng & khách", office: true,
    title: "Thu tiền hàng loạt",
    desc: "Thu nợ của nhiều khách trong một lần — tick khách, nhập số, tạo phiếu thu gộp.",
    routes: ["#/thu-tien"],
    sections: [
      { title: "Trang này để làm gì?", html: `
        <p>Trang <a href="#/thu-tien">Thu tiền hàng loạt</a> giúp <b>văn phòng thu nợ của nhiều khách cùng lúc</b>:
        chọn các khách đang nợ → nhập số thu từng khách → bấm thu một lần, hệ thống tạo phiếu thu cho từng khách.</p>
        <p class="muted small">Vào bằng menu <b>☰ Thêm → Tài chính → Thu tiền</b>. <b>Chỉ văn phòng</b> mới thấy và thu được.</p>` },
      { title: "Các bước thu", html: `
        <ol>
          <li>Đầu trang thấy <b>số khách đang nợ</b> và <b>tổng thu được</b>. Gõ ô tìm (không dấu) để lọc khách.</li>
          <li>Bấm vào từng khách để <b>tick chọn</b> — mỗi khách tự điền sẵn số thu tối đa. Hoặc bấm
            <b>Chọn tất cả — thu đủ</b>.</li>
          <li>Sửa số tiền của từng khách nếu chỉ thu một phần.</li>
          <li>Chọn hình thức: <b>TM</b> (tiền mặt) hay <b>CK</b> (chuyển khoản).</li>
          <li>Bấm <b>Thu tiền</b> → xác nhận. Kết quả từng khách (thành công / lỗi) hiện ở đầu trang.</li>
        </ol>
        <p class="muted small">Không nhập vượt <b>số thu được qua đơn</b> của khách (báo "tối đa qua đơn"). Nợ KiotViet chỉ để tham chiếu.</p>` },
      { title: "\"Nộp tiền\" khác \"phiếu thu\"", html: `
        <p>Đừng nhầm hai việc:</p>
        <ul>
          <li><b>Nộp tiền</b>: <i>shipper</i> báo đã giao / đã thu tiền khách (bước trong đơn).</li>
          <li><b>Phiếu thu</b>: <i>văn phòng</i> ghi nhận đã nhận tiền → <b>giảm nợ khách</b>. Trang này tạo phiếu thu.</li>
        </ul>
        <p>Muốn hiểu tiền chạy về két nào, xem bài <a href="#/huong-dan/ket-tien">Két tiền</a>.</p>` },
      { title: "Tiền vào két nào?", html: `
        <ul>
          <li>Thu <b>chuyển khoản</b> → vào <b>Két ngân hàng</b>.</li>
          <li>Thu <b>tiền mặt</b> → vào <b>két của người tạo phiếu thu</b> (người đang đăng nhập).</li>
        </ul>` },
    ],
  },
  {
    key: "tra-hang", icon: "refresh", cat: "Đơn hàng & khách",
    title: "Trả hàng (đổi/hoàn)",
    desc: "Tạo phiếu trả, xuất hoá đơn giá âm để trừ nợ, rồi xử lý hàng trả về.",
    routes: ["#/tra-hang"],
    sections: [
      { title: "Trả hàng hoạt động thế nào?", html: `
        <p>Trang <a href="#/tra-hang">Trả hàng</a> ghi nhận hàng khách trả lại. KiotViet <b>không có
        chức năng trả hàng</b> qua API, nên hệ thống dùng cách: tạo một <b>hoá đơn KiotViet giá âm</b>
        (số lượng dương × đơn giá âm) để <b>trừ thẳng vào nợ khách</b>.</p>` },
      { title: "Flow giống đơn hàng", html: `
        <ol>
          <li>Bấm <b>Tạo phiếu</b> → phiếu ở trạng thái <b>Nháp</b>: <i>chưa</i> đụng KiotViet, <i>chưa</i> đổi nợ,
            còn <b>sửa được</b>.</li>
          <li>Kiểm xong, bấm <b>Tạo HĐ KiotViet (trừ nợ …)</b> (văn phòng): sinh hoá đơn giá âm,
            <b>trừ nợ khách ngay</b>, và <b>khoá sửa</b> phiếu.</li>
          <li>Cần huỷ? <b>Admin</b> bấm <b>Xoá HĐ KiotViet (hoàn nợ)</b> → phiếu về Nháp, nợ cộng lại; hoặc xoá hẳn phiếu.</li>
        </ol>` },
      { title: "Xử lý hàng trả về", html: `
        <p>Ngay sau khi tạo phiếu, hệ thống hỏi <b>"Xử lý hàng trả về ngay?"</b> (<b>Xử lý ngay</b> / <b>Để sau</b>).
        Với mỗi dòng hàng, chọn một cách:</p>
        <ul>
          <li><b>Nhập vào thùng có sẵn</b> — cộng số lượng vào một thùng đang chứa mặt hàng đó.</li>
          <li><b>Tạo thùng mới</b> — mở thùng mới cho số hàng trả về.</li>
          <li><b>Xuất hủy</b> — hàng hư/không dùng được, ghi nhận huỷ.</li>
          <li><b>Bỏ qua</b> — chưa xử lý, để sau.</li>
        </ul>
        <p class="muted small">Mỗi phiếu chỉ xử lý hàng <b>một lần</b>; xử lý xong hiện tóm tắt kết quả. Để sau vẫn mở lại được từ chi tiết phiếu.</p>` },
      { title: "Ảnh, trao đổi & lịch sử", html: `
        <p>Mỗi phiếu trả có <b>ảnh</b>, <b>trao đổi</b> (chat) và <b>lịch sử thao tác</b> — tiện đối chiếu khi có
        tranh cãi về hàng trả.</p>` },
    ],
  },
  {
    key: "viec", icon: "check", cat: "Đơn hàng & khách",
    title: "Việc cần làm (task)",
    desc: "Danh sách việc: việc tự tạo + các bước của đơn; tick xong ghi ngược về đơn.",
    routes: ["#/viec"],
    sections: [
      { title: "Trang Việc là gì?", html: `
        <p>Trang <a href="#/viec">Việc cần làm</a> gom mọi việc phải làm về một chỗ. Có <b>hai loại</b> việc:</p>
        <ul>
          <li><b>Việc tự tạo</b> — bạn tự thêm; có thể <i>gắn kèm một đơn</i> nếu liên quan.</li>
          <li><b>Việc của đơn</b> — <b>bám theo các bước của đơn</b> (soạn hàng / giao hàng / nộp tiền…),
            tự sinh ra từ đơn.</li>
        </ul>` },
      { title: "Tick xong ghi ngược về đơn", html: `
        <p>Với việc của đơn, <b>tick "xong" ở đây sẽ ghi ngược về đơn</b> — bước tương ứng của đơn cũng
        được đánh dấu hoàn tất. Không cần vào đơn tick lại. (Đơn vẫn là nguồn sự thật; trang Việc là bản
        soi chiếu để bạn làm nhanh.)</p>` },
      { title: "Lọc, tìm, xem theo lịch", html: `
        <ul>
          <li>Ô KPI lọc theo trạng thái: <b>Đang mở · Của tôi · Quá hạn · Xong</b>.</li>
          <li>Chips lọc theo loại: <b>Việc tự do · Việc thêm · Từ đơn</b>.</li>
          <li>Ô <b>tìm không dấu</b> ("Tìm việc, đơn, người làm…") để tìm theo tên/nội dung/người làm.</li>
          <li>Danh sách <b>cuộn tải thêm</b> dần khi kéo xuống.</li>
          <li>Nút chuyển <b>Danh sách ⇄ Lịch</b> để xem việc <b>theo lịch</b> (từng ngày).</li>
        </ul>` },
      { title: "Chuông việc & chi tiết", html: `
        <p><b>Chuông việc</b> trên thanh trên cùng hiện <b>số việc của tôi</b> — nhắc bạn còn việc chưa làm.</p>
        <p>Bấm vào một việc để mở <b>chi tiết việc</b> (<a href="#/viec">#/viec/…</a>): mô tả, người phụ trách,
        đơn liên quan, kèm <b>ảnh / trao đổi</b>.</p>` },
    ],
  },
  {
    key: "lich-giao", icon: "calendar", cat: "Đơn hàng & khách",
    title: "Lịch giao & ai đang giao",
    desc: "Lịch giao theo ngày, filter Chưa giao tới hạn, và danh sách đơn đang trên đường.",
    routes: ["#/lich", "#/dang-giao"],
    sections: [
      { title: "Lịch giao theo ngày", html: `
        <p>Trang <a href="#/lich">Lịch giao</a> là lịch cuộn liền mạch (kiểu macOS). Mỗi ô ngày hiện
        <b>nhãn từng đơn</b> giao trong ngày đó:</p>
        <ul>
          <li><b>Đỏ</b> = đơn <b>chưa giao</b>.</li>
          <li><b>Xanh</b> = đơn <b>đã giao</b>.</li>
        </ul>
        <p>Cuộn <b>vô hạn hai chiều</b> (tháng nào cũng lướt tới được), có nút <b>Hôm nay</b> để nhảy về ngày hiện tại.
        Bật <b>Ẩn đã giao</b> để chỉ còn đơn chưa giao. Bấm một ngày để xem danh sách đơn của ngày đó.</p>` },
      { title: "Lịch ngay trong dashboard Đơn", html: `
        <p>Ở trang <a href="#/orders">Đơn</a>, thanh chọn kiểu xem có ô <b>📅 lịch giao</b> — xem nhanh lịch mà
        không rời dashboard.</p>` },
      { title: "Filter \"Chưa giao\" = tới hạn", html: `
        <p>Bộ lọc <b>Chưa giao</b> chỉ đếm đơn <b>tới hạn</b>: đơn <i>chưa hẹn ngày</i>, hoặc <i>ngày giao ≤ hôm nay</i>.
        Đơn hẹn giao ngày mai chưa tính là "chưa giao" — nên con số phản ánh đúng <b>việc cần làm hôm nay</b>.</p>` },
      { title: "Ai đang giao", html: `
        <p>Trang <a href="#/dang-giao">Ai đang giao</a> gom đơn <b>đã giao nhưng chưa nộp tiền</b>, xếp theo người
        đang giữ — biết ngay ai đang cầm đơn nào, giữ bao lâu, bao nhiêu tiền.</p>
        <p class="muted small">Không tính đơn hẹn "Chiều lấy tiền". Dùng chung mốc ngày với hệ Két tiền.</p>` },
    ],
  },
];
