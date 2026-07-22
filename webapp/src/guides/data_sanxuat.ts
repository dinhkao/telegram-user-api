// Hướng dẫn SẢN XUẤT (phiếu SX/tiền công/thợ) — dữ liệu tĩnh (xem guides/types.ts). Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_SANXUAT: Guide[] = [
  {
    key: "san-xuat", icon: "factory", cat: "Sản xuất",
    title: "Phiếu sản xuất & báo cáo thợ",
    desc: "Tạo phiếu SX, nhập số thùng, ghi báo cáo theo từng thợ, xem dashboard sản lượng.",
    routes: ["#/san_xuat", "#/sx-bang", "#/sx-tho"],
    sections: [
      { title: "Phiếu sản xuất là gì?", html: `
        <p>Trang <a href="#/san_xuat">Sản xuất</a> (tab <b>🏭 SX</b> dưới cùng) là danh sách các
        <b>phiếu sản xuất</b>. Mỗi phiếu là <i>một mẻ làm hàng</i>: bấm <b>Tạo phiếu</b> sẽ mở một
        <b>topic (chủ đề) trong nhóm sản xuất trên Telegram</b> — mọi người báo cáo qua lại ngay trong đó,
        và app đọc lại để hiện ra bảng.</p>
        <p>Trong mỗi phiếu bạn:</p>
        <ul>
          <li>Chọn <b>mã sản phẩm</b> đang làm.</li>
          <li>Đặt <b>mục tiêu</b> (target) — số lượng dự kiến của mẻ.</li>
          <li><b>Thêm số thùng</b> khi hàng ra thùng (nhập kho thành phẩm).</li>
        </ul>
        <p class="muted small">Danh sách lọc nhanh bằng chip <b>Tất cả · Sản xuất · Đóng gói · Ngày</b>.
          Mỗi card so sánh <b>số nhập thùng</b> với <b>số báo cáo thợ</b>: khớp thì ✅, lệch thì ⚠️.</p>` },
      { title: "2 loại phiếu: Sản xuất vs Đóng gói", html: `
        <p>Có <b>hai loại phiếu</b>, khác nhau ở chỗ trừ nguyên liệu:</p>
        <ul>
          <li><b>Phiếu SẢN XUẤT</b> — làm ra hàng, <i>không cần</i> chọn nguyên liệu chính. Dùng cho sản phẩm
            làm trực tiếp.</li>
          <li><b>Phiếu ĐÓNG GÓI</b> — <b>bắt buộc</b> sản phẩm phải có <b>công thức (BOM)</b> và bạn phải
            <b>chọn đủ thùng nguyên liệu</b> cho từng thành phần → hệ thống <b>trừ kho nguyên liệu</b> tự động.</li>
          <li>SP có khai <b>nguyên liệu phụ</b> (bao bì/tem…) và đang bật <b>「Yêu cầu khi sản xuất」</b>
            ở chi tiết SP → <b>cả hai loại phiếu</b> đều phải chọn thêm thùng NL phụ (dòng có nhãn <i>(phụ)</i>) để trừ kho.
            Có <b>kho đặc biệt nguồn NL phụ</b> (⭐ ở chi tiết vị trí kho) → chỉ chọn được thùng đang ở kho đó.</li>
        </ul>
        <p class="muted small">Công thức (nguyên liệu + tỉ lệ) khai báo ở chi tiết sản phẩm trong
          <a href="#/san-pham">Sản phẩm</a>. Xem thêm bài hướng dẫn Kho & Sản phẩm.</p>
        <p class="muted small">Lưu ý: khi đã <b>nhập ít nhất 1 thùng</b> vào phiếu thì <b>loại phiếu bị khoá</b>
          (không đổi qua lại được nữa) — chọn đúng loại ngay từ đầu.</p>` },
      { title: "Báo cáo theo từng thợ", html: `
        <p>Mở một phiếu (<a href="#/san_xuat">#/san_xuat/:id</a>) sẽ thấy <b>bảng báo cáo</b> — mỗi dòng là
        một thợ, các cột: <b>Tên · Gạch · Trừ · Lẻ · Ghi chú</b>. Cột <b>Mâm</b> và <b>Tổng</b> app
        <i>tự tính</i> theo cấu hình mâm/lượng của sản phẩm, bạn không phải cộng tay.</p>
        <p>Báo cáo luôn <b>xem được</b> ngay trong phiếu. Muốn sửa thì bấm nút <b>✏️ Sửa</b> để mở
        trang nhập riêng.</p>` },
      { title: "Sửa báo cáo (trang nhập riêng)", html: `
        <p>Bấm <b>✏️ Sửa</b> → mở trang <a href="#/san_xuat">#/san_xuat/:id/bao-cao</a>: một
        <b>bảng nhập kiểu bảng tính</b> (spreadsheet). Gõ Tên/Gạch/Trừ/Lẻ/Ghi chú theo từng dòng,
        Mâm và Tổng tự chạy. Xong bấm <b>Lưu</b>.</p>
        <p><b>Khoá một người sửa:</b> mỗi lúc chỉ <b>một người</b> được sửa báo cáo của một phiếu.</p>
        <ul>
          <li>Người khác đang sửa → bạn thấy báo <b>「... đang sửa」</b> và <i>xem được họ gõ trực tiếp</i>.</li>
          <li>Nếu người khác đang giữ khoá, thao tác <b>Lưu</b> của bạn sẽ bị <b>chặn</b> — chờ họ xong.</li>
        </ul>
        <p><b>Mẹo nhập nhanh:</b></p>
        <ul>
          <li>App <b>tự lưu</b> sau khi bạn ngừng gõ (~1,5 giây) — không phải bấm Lưu liên tục.</li>
          <li>Nhấn <b>Enter</b> để nhảy xuống ô cùng cột ở dòng dưới. Bấm vào ô là bôi đen sẵn, gõ đè luôn.</li>
          <li>Nút <b>「Chọn/sắp thợ」</b> để thêm/bớt thợ trong bảng.</li>
          <li>Nút <b>「Ảnh nền để dò」</b>: gắn ảnh phiếu giấy làm nền để đối chiếu; giữ nút 👁️ (hoặc phím K) để xem ảnh.</li>
          <li>Cột <b>「SP đè」/「Mâm đè」</b> để nhập tay đè số tự tính khi cần (dùng khi công thức không khớp thực tế).</li>
        </ul>` },
      { title: "Lương theo giờ (cột Giờ)", html: `
        <p>Với <b>phiếu sản xuất</b>, bảng báo cáo có thêm cột <b>Giờ</b>. Dòng nào có nhập số giờ thì
        tiền công của thợ đó tính theo <b>giờ × đơn giá giờ</b> (thay cho cây × đơn giá).</p>
        <p>Đơn giá giờ của mỗi thợ đặt ở <b>chi tiết thợ</b> (<a href="#/sx-tho">#/sx-tho/:name</a>) — xem
        bài <a href="#/huong-dan/tho">Thợ</a>. Thợ có nhập giờ mà <i>chưa đặt đơn giá giờ</i> sẽ hiện
        cảnh báo và dòng tạm tính 0đ.</p>` },
      { title: "Dashboard sản xuất & xem theo thợ", html: `
        <p>Vào <a href="#/sx-bang">#/sx-bang</a> (menu <b>☰ Thêm</b> → Dashboard SX) để xem
        <b>tổng sản lượng</b>. Bấm vào <b>một thợ</b> → mở <a href="#/sx-tho">#/sx-tho/:name</a>:
        chi tiết của thợ đó, bóc tách theo <b>ngày</b> và theo <b>từng sản phẩm</b>.</p>` },
    ],
  },
  {
    key: "tien-cong", icon: "wallet", cat: "Sản xuất", office: true,
    title: "Tiền công & lương sản phẩm",
    desc: "Đơn giá /1 sản phẩm, lương chốt theo phiếu, phiếu báo cáo tính lương theo khoảng ngày.",
    routes: ["#/tien-cong", "#/luong-sp", "#/bao-cao"],
    sections: [
      { title: "Tiền công thợ", html: `
        <p>Trang <a href="#/tien-cong">Tiền công</a> tổng hợp <b>tiền công của các thợ</b>: dựa trên số
        cây (hoặc số giờ) đã báo cáo × đơn giá tương ứng. Số liệu tính <b>tự động</b> từ báo cáo của các
        phiếu sản xuất.</p>` },
      { title: "Bảng đơn giá /1 sản phẩm (Lương SP)", html: `
        <p><a href="#/luong-sp">#/luong-sp</a> (chỉ <b>văn phòng</b>) là bảng <b>đơn giá tiền công cho 1 sản phẩm</b>:
        mỗi mã SP làm ra một cây được trả bao nhiêu tiền công.</p>
        <ul>
          <li>Sửa đơn giá xong, <b>tiền công tính lại ngay</b> — không cần thao tác gì thêm.</li>
          <li>Đặt lương <b>≤ 0</b> = <b>gỡ mã</b> đó khỏi bảng (mã sẽ báo thiếu đơn giá cho tới khi đặt lại).</li>
        </ul>` },
      { title: "Lương CHỐT THEO PHIẾU", html: `
        <p>Đây là điểm quan trọng: <b>mỗi phiếu SX chốt đơn giá /1SP tại thời điểm gán sản phẩm</b> vào phiếu.
        Nghĩa là:</p>
        <ul>
          <li>Sau này bạn <b>sửa bảng lương</b> thì <b>không ảnh hưởng</b> tới các phiếu đã chốt trước đó.</li>
          <li>Phiếu cũ giữ nguyên đơn giá lúc làm → tiền công lịch sử không bị lệch.</li>
        </ul>
        <p>Cần chỉnh riêng một phiếu? Văn phòng vào chi tiết phiếu, sửa ô <b>「Đơn giá phiếu này」</b>
        trong khối tiền công (chỉ áp dụng cho đúng phiếu đó).</p>` },
      { title: "Phiếu báo cáo lương (theo khoảng ngày)", html: `
        <p><a href="#/bao-cao">#/bao-cao</a> (chỉ <b>văn phòng</b> — đây là <b>tiền lương</b>) dùng để làm phiếu
        lương: bấm tạo phiếu, <b>chọn khoảng ngày</b> (có sẵn preset <i>Tuần này / Tuần trước</i>).</p>
        <p>Nội dung phiếu <b>tính live mỗi lần mở</b>:</p>
        <ul>
          <li>Tổng sản phẩm + <b>tiền theo từng thợ</b>.</li>
          <li>Tiền của <b>từng phiếu SX</b> trong khoảng ngày, và tổng cộng.</li>
        </ul>` },
      { title: "Chọn thợ & preset Lương tuần", html: `
        <p>Khi tạo phiếu báo cáo có thể <b>chọn thợ</b> (chip chọn từng người) hoặc để trống = <b>mọi thợ</b>.
        Preset <b>「Lương tuần」</b> tự chọn đúng nhóm thợ đã bật cờ <i>lương tuần</i> (xem bài
        <a href="#/huong-dan/tho">Thợ</a>).</p>` },
      { title: "Ai được làm gì?", html: `
        <ul>
          <li>Xem/tạo phiếu báo cáo lương, sửa bảng đơn giá: <b>văn phòng</b>.</li>
          <li><b>Xoá</b> phiếu báo cáo: chỉ <b>admin</b>.</li>
        </ul>` },
    ],
  },
  {
    key: "tho", icon: "users", cat: "Sản xuất",
    title: "Thợ (nhân công)",
    desc: "Danh sách thợ, danh tính bất biến, đơn giá giờ, cờ lương tuần, sắp xếp thứ tự.",
    routes: ["#/tho"],
    sections: [
      { title: "Danh sách thợ", html: `
        <p>Trang <a href="#/tho">Thợ</a> quản lý danh sách <b>nhân công sản xuất</b>. Đây là nguồn tên thợ
        dùng trong mọi bảng báo cáo và bảng lương.</p>` },
      { title: "Đổi tên thợ — danh tính bất biến", html: `
        <p>Mỗi thợ có một <b>danh tính riêng (id) không đổi</b>, còn <i>tên chỉ là nhãn</i>. Nhờ vậy, khi bạn
        <b>đổi tên</b> một thợ:</p>
        <ul>
          <li>Tên mới <b>tự cập nhật khắp mọi phiếu và báo cáo</b> — kể cả phiếu cũ.</li>
          <li><b>Không bị tách lịch sử</b>: sản lượng và tiền công của thợ vẫn gộp về đúng một người.</li>
        </ul>
        <p class="muted small">Cứ đổi tên thoải mái khi thợ đổi biệt danh — dữ liệu không vỡ.</p>` },
      { title: "Đơn giá giờ (lương theo giờ)", html: `
        <p>Vào <b>chi tiết thợ</b> <a href="#/sx-tho">#/sx-tho/:name</a>, ô <b>「Tiền 1 giờ làm」</b>
        (chỉ <b>văn phòng</b>). Đây là con số dùng cho <b>lương theo giờ</b>: dòng báo cáo có nhập cột
        <b>Giờ</b> sẽ tính tiền = <b>giờ × đơn giá giờ</b> của thợ. Chưa đặt mà đã có giờ → app cảnh báo
        <i>「chưa đặt tiền 1 giờ」</i>.</p>` },
      { title: "Cờ Nhận lương tuần", html: `
        <p>Ở chi tiết thợ có công tắc <b>「Nhận lương tuần」</b>. Bật nó để thợ đó lọt vào preset <b>Lương tuần</b>
        khi tạo <a href="#/bao-cao">phiếu báo cáo lương</a> — tiện gom đúng nhóm thợ ăn lương theo tuần
        mà không phải chọn tay mỗi lần.</p>` },
      { title: "Xem sản lượng của thợ", html: `
        <p>Chi tiết thợ <a href="#/sx-tho">#/sx-tho/:name</a> còn cho xem <b>sản phẩm theo ngày</b> của thợ:
        bóc tách từng ngày / từng SP để đối chiếu công và lương.</p>` },
      { title: "Sắp xếp thứ tự thợ", html: `
        <p>Có trang <a href="#/tho">#/tho/sap-xep</a> để <b>sắp xếp lại thứ tự</b> hiển thị các thợ — kéo cho
        người hay nhập lên đầu, tiện chọn nhanh trong bảng báo cáo.</p>` },
    ],
  },
  {
    key: "cham-cong", icon: "clock", cat: "Sản xuất",
    title: "Chấm công (máy Ronald Jack)",
    desc: "Xem giờ vào/ra từ máy chấm công vân tay; gán mã NV trên máy cho từng thợ.",
    routes: ["#/cham-cong"],
    sections: [
      { title: "Dữ liệu từ đâu ra?", html: `
        <p>Máy chấm công vân tay <b>Ronald Jack</b> ở văn phòng tự đẩy dữ liệu lên hệ thống
        <b>30 phút một lần</b>. Không cần thao tác gì — nhân viên chấm trên máy, dữ liệu tự về.</p>
        <p>Trang <a href="#/cham-cong">Chấm công</a> (☰ Thêm → Lương) là <b>lưới cả tháng</b>:
        cột đầu là tên nhân viên (đứng yên), mỗi ngày 1 cột gồm <b>3 ống</b> = ca sáng 7–11,
        ca chiều 13–17 và ống <b>tăng ca</b> 17–21 (tím, mảnh, viền đứt). Ống <b>xanh đầy</b> =
        chấm đủ ca; xanh một phần = có mặt một đoạn; <b>tím</b> = giờ tăng ca chiều tối;
        <b>vạch cam</b> = chỉ chấm 1 lần (thiếu vào/ra); trống = không chấm. Tổng giờ tăng ca
        cả tháng (có mặt ngoài 2 khung ca — kể cả xuyên trưa/trước 7h) hiện <b>tím cạnh tên</b>,
        vd "TC 12g30". <b>Kéo ngang</b> để xem hết tháng, bấm vào 1 ống để xem giờ chấm chi
        tiết. Đầu trang có dòng <i>cập nhật gần nhất</i> và giờ máy gửi lần kế.</p>` },
      { title: "Gán mã NV trên máy cho thợ", html: `
        <p>Mọi người đều <b>xem</b> được trang Chấm công; riêng <b>gán mã</b> và <b>sửa giờ</b>
        (ẩn giờ máy, thêm/xoá giờ tay) chỉ tài khoản <b>văn phòng</b> làm được.</p>
        <p>Máy chỉ biết <b>mã số</b> (11, 95…), hệ thống cần biết mã đó là <b>ai</b>. Có 2 chỗ gán:</p>
        <ul>
          <li>Khu <b>"Mã máy chưa gán thợ"</b> đầu trang Chấm công — chọn thợ cho từng mã lạ;</li>
          <li>Ô <b>"ID chấm công"</b> trong trang chi tiết thợ (<a href="#/sx-bang">Dashboard SX</a> → bấm tên) —
          nhập mã máy của người đó (một người có thể có nhiều mã; bấm ✕ để gỡ).</li>
        </ul>
        <p>Gán xong, toàn bộ lịch sử chấm cũ của mã đó cũng tự tính cho đúng người.</p>` },
      { title: "Nghi chấm thiếu — máy tự soi", html: `
        <p>Khu <b>"⚠ Nghi chấm thiếu"</b> tự quét cả tháng và liệt kê các ca bất thường:</p>
        <ul>
          <li>chấm <b>số lần lẻ</b> trong ngày (thiếu 1 lần vào hoặc ra — kèm gợi ý ca nào);</li>
          <li>cặp vào-ra <b>quá gần nhau</b> trong ca (vd 13:40→13:47 — nghi bấm 2 lần liền, quên chấm ra);</li>
          <li>vào-ra <b>xuyên trọn giờ trưa</b> không chấm giữa (vd 7:00→17:00 — nghi quên chấm trưa;
          khoảng 11–13h này <b>không</b> bị tính nhầm thành tăng ca).</li>
        </ul>
        <p>Dùng danh sách này để nhắc nhân viên chấm đủ vào/ra từng buổi.</p>` },
      { title: "Lưu ý", html: `
        <p>Chấm công đã <b>nối vào Bảng lương tháng</b>: thợ <i>lương thời gian</i> đặt
        <b>Mốc lương tháng</b> (cột "Mốc" / dòng Mốc trên thẻ) → lương thực = mốc ÷ 26 ×
        <b>ngày công</b> (ngày đủ 2 ca = 1 công, tính từ giờ chấm), <b>tăng ca ×1,2</b>
        (chỉ tính khi chấm ra trễ hơn 15 phút sau giờ hết ca; ca xuyên trưa không chấm
        giữa không tính tăng ca trưa). Giờ sửa tay trong popup cũng được tính.</p>` },
    ],
  },
];
