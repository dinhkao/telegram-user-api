// Hướng dẫn CHUYỂN KHO / XUẤT HỦY / NHẬP HÀNG & NCC — dữ liệu tĩnh (xem guides/types.ts). Gom ở guides/registry.ts.
import type { Guide } from "./types";

export const GUIDES_KHONHAP: Guide[] = [
  {
    key: "chuyen-kho", icon: "truck", cat: "Kho & hàng hoá",
    title: "Chuyển kho hàng loạt",
    desc: "Dời nhiều thùng sang vị trí kho khác cùng lúc, theo 3 bước.",
    routes: ["#/chuyen-kho"],
    sections: [
      { title: "Dùng để làm gì?", html: `
        <p>Trang <a href="#/chuyen-kho">Chuyển kho hàng loạt</a> giúp <b>dời nhiều thùng
        sang một vị trí kho khác trong một lần</b> — thay vì mở từng thùng để sửa vị trí.</p>
        <p>Ví dụ: dọn hết hàng từ <i>Kho A</i> sang <i>Kho B</i>, hoặc gom hàng cùng loại
        về một chỗ cho gọn.</p>
        <p class="muted small">Chỉ chuyển được thùng <b>còn hàng và chưa bị vô hiệu hoá</b>.
        Vào trang này bằng nút <b>Chuyển kho</b> ở dashboard <a href="#/kho">📦 Kho</a>.</p>` },
      { title: "Làm theo 3 bước", html: `
        <ol>
          <li><b>1 · Kho nguồn</b> — bấm chọn vị trí kho đang chứa hàng cần dời.
            Chọn <b>Ko có kho</b> để lấy các thùng chưa được gán vị trí. Con số bên cạnh
            mỗi lựa chọn là <i>số thùng chuyển được</i> ở đó.</li>
          <li><b>2 · Chọn thùng</b> — tick các thùng muốn dời. Có ô tìm theo
            <b>mã SP / số thùng</b> và nút <b>Chọn tất cả</b> (áp dụng cho các thùng đang hiện sau khi lọc).</li>
          <li><b>3 · Kho đích</b> — bấm chọn vị trí muốn chuyển tới (kho nguồn tự bị loại ra).</li>
        </ol>
        <p>Cuối trang bấm nút <b>「Chuyển … thùng → kho đích」</b>, xác nhận là xong.
        Xong sẽ báo đã chuyển bao nhiêu thùng (và bao nhiêu bị bỏ qua nếu có).</p>` },
      { title: "Số lượng có bị thay đổi không?", html: `
        <p><b>Không.</b> Chuyển kho chỉ đổi <b>vị trí</b> của thùng — số lượng trong thùng
        và tồn kho tổng <b>giữ nguyên</b>. Đây không phải là xuất hay hủy hàng.</p>
        <p class="muted small">Muốn <i>gộp hàng cùng SP từ thùng này sang thùng kia</i>
        (dồn hàng, đổi số lượng giữa 2 thùng) thì làm ở <b>chi tiết thùng</b>
        (<a href="#/kho">📦 Kho</a> → mở thùng → chức năng chuyển hàng) — tồn tổng vẫn bảo toàn.</p>` },
      { title: "Mẹo", html: `
        <ul>
          <li>Lọc theo <b>mã SP</b> rồi bấm <b>Chọn tất cả</b> để dời nhanh toàn bộ một loại hàng.</li>
          <li>Dời nhầm? Chạy lại chuyển kho theo chiều ngược lại — không mất số lượng.</li>
          <li>Danh sách tự cập nhật khi kho có biến động (người khác nhập/xuất) — không cần tải lại.</li>
        </ul>` },
    ],
  },
  {
    key: "xuat-huy", icon: "trash", cat: "Kho & hàng hoá",
    title: "Xuất hủy hàng hoá",
    desc: "Ghi nhận hàng hư/hết hạn, trừ tồn kho; hoặc hủy hàng khách trả.",
    routes: ["#/xuat-huy"],
    sections: [
      { title: "Xuất hủy là gì?", html: `
        <p>Trang <a href="#/xuat-huy">Xuất hủy</a> ghi lại các lần <b>bỏ hàng</b> — hàng hư,
        hết hạn, vỡ, hoặc hàng khách trả về không dùng được. Mọi phiếu hủy được nhóm theo ngày;
        bấm vào một phiếu để xem chi tiết (<a href="#/xuat-huy">#/xuat-huy/:id</a>).</p>
        <p>Có <b>hai loại phiếu hủy</b>, khác nhau ở chỗ <i>có trừ tồn kho hay không</i> — xem 2 mục dưới.</p>` },
      { title: "Loại 1 · Hủy theo thùng (TRỪ TỒN)", html: `
        <p>Dùng khi hàng trong kho bị hư/hết hạn. Phiếu này <b>trừ thẳng tồn kho</b> của thùng bị hủy.</p>
        <ol>
          <li>Vào <a href="#/kho">📦 Kho</a> → mở đúng <b>thùng</b> có hàng cần bỏ (<a href="#/kho">#/thung/:id</a>).</li>
          <li>Bấm <b>Xuất hủy</b> — <b>bắt buộc chụp ảnh</b> hàng hư trước (làm bằng chứng),
            rồi ghi <b>lý do</b>.</li>
        </ol>
        <p class="muted small">Tồn thùng <b>giảm ngay</b> khi tạo phiếu. Nếu bấm nhầm,
        <b>admin</b> vào phiếu bấm <b>Xoá</b> → tồn kho được <b>hoàn lại</b> vào thùng.</p>` },
      { title: "Loại 2 · Hủy hàng khách trả (KHÔNG trừ tồn)", html: `
        <p>Khi khách trả hàng mà hàng đó không nhập lại kho được, ta <b>hủy</b> luôn phần đó.
        Loại này chỉ <b>GHI NHẬN</b> để có sổ sách — <b>không trừ tồn kho</b> (vì hàng chưa từng
        vào lại kho). Phiếu có nhãn <b>hàng trả</b> và liên kết về phiếu trả gốc.</p>
        <p class="muted small">Loại này thường được tạo tự động khi bạn <b>xử lý hàng trả về</b>
        và chọn “Xuất hủy” cho một dòng hàng (xem bài <a href="#/huong-dan/tra-hang">Trả hàng</a>).</p>` },
      { title: "Bắt buộc & cần nhớ", html: `
        <ul>
          <li><b>Luôn phải nhập lý do</b> — không có lý do thì không tạo được phiếu.</li>
          <li>Hàng trong phiếu là <b>ảnh chụp tại thời điểm hủy</b> (snapshot) — sau này đổi
            tên/mã SP cũng không làm sai phiếu cũ.</li>
          <li>Phiếu hủy có <b>ảnh · trao đổi · lịch sử</b> riêng để đối chiếu về sau.</li>
          <li>Xoá phiếu là quyền <b>admin</b>: hủy-theo-thùng xoá thì hoàn tồn; hủy-hàng-trả
            xoá chỉ gỡ bản ghi (không có tồn để hoàn).</li>
        </ul>` },
      { title: "Xem nhanh", html: `
        <ul>
          <li>Ô tìm ở đầu trang lọc theo <b>lý do · mã SP · số thùng · người tạo</b>.</li>
          <li>Trong phiếu, bấm số thùng để nhảy về <b>chi tiết thùng</b>.</li>
          <li>Danh sách tự cập nhật khi có phiếu mới — không cần tải lại.</li>
        </ul>` },
    ],
  },
  {
    key: "nhap-hang", icon: "truck", cat: "Kho & hàng hoá",
    title: "Nhập hàng & nhà cung cấp",
    desc: "Ghi phiếu mua hàng của nhà cung cấp và trả tiền NCC từ két.",
    routes: ["#/nhap-hang", "#/ncc"],
    sections: [
      { title: "Nhập hàng để làm gì?", html: `
        <p>Trang <a href="#/nhap-hang">Nhập hàng</a> ghi lại các <b>phiếu mua hàng của nhà cung cấp
        (NCC)</b>: mua gì, số lượng, giá, của ai. Đây là sổ sách <b>100% nội bộ</b> — không đẩy lên
        KiotViet. Phiếu nhóm theo ngày, cuộn xuống để xem thêm; bấm một phiếu để mở chi tiết.</p>
        <p class="muted small">Ai cũng xem được. <b>Tạo và sửa</b> phiếu là quyền <b>văn phòng</b>;
        <b>xoá</b> là quyền <b>admin</b> (xoá mềm).</p>` },
      { title: "Tạo phiếu nhập", html: `
        <ol>
          <li>Ở <a href="#/nhap-hang">#/nhap-hang</a> bấm <b>Tạo phiếu</b> (hoặc tạo ngay trong trang một NCC).</li>
          <li><b>Chọn nhà cung cấp</b> — gõ tên để tìm. Gõ tên <i>chưa có trong danh sách</i> sẽ hiện
            <b>「➕ Tạo NCC mới」</b> — bấm là tạo NCC ngay, khỏi qua trang khác.</li>
          <li><b>Thêm dòng hàng</b>: gõ <b>mã SP</b> (dùng chung bảng sản phẩm; chỉ gợi ý SP được phép
            nhập, mã lạ vẫn gõ tay được), <b>số lượng</b>, <b>giá nhập</b>. Bấm <b>Thêm dòng</b> cho nhiều mặt hàng.</li>
          <li>SP có <b>quy đổi đơn vị</b> (khai ở chi tiết SP) → dưới dòng hiện ô <b>Đơn vị nhập</b>:
            chọn thùng/kiện… thì <b>SL + giá tính theo đơn vị đó</b>, app tự quy ra đơn vị gốc
            (vd 3 thùng = 90 cây) và điền sẵn khi nhập kho.</li>
          <li>Ghi <b>ghi chú</b> nếu cần, xem <b>Tổng nhập</b>, rồi bấm <b>Tạo phiếu nhập</b>.</li>
        </ol>
        <p class="muted small">Mỗi phiếu có <b>ảnh · trao đổi · lịch sử</b> riêng. Sửa hàng/ghi chú ở
        nút <b>Sửa</b> trong phiếu (văn phòng).</p>` },
      { title: "Nhập kho hàng mua về", html: `
        <p>Tạo phiếu xong app hỏi <b>「Nhập kho hàng mua về ngay?」</b> — hoặc bấm nút
        <b>「Nhập kho hàng mua về」</b> trong chi tiết phiếu (văn phòng). Mỗi dòng hàng chọn:</p>
        <ul>
          <li><b>🆕 Tạo thùng mới</b> (mặc định) — chọn vị trí kho + đơn vị chứa; thùng mới
            gắn link ngược về phiếu nhập.</li>
          <li><b>📦 Nhập vào thùng có sẵn</b> — cộng tồn vào một thùng cùng mã SP đang còn hàng.</li>
          <li><b>Bỏ qua</b> — hàng không quản kho.</li>
        </ul>
        <ul>
          <li>Sửa được <b>số lượng thực nhận</b> nếu hàng về thiếu/vỡ so với phiếu.</li>
          <li>Nhập kho <b>1 lần/phiếu</b>. Sau khi nhập, phiếu <b>khoá sửa hàng</b> và
            <b>không xoá được</b> (hàng đã vào thùng); danh sách phiếu hiện chip
            <span class="cash-badge ok">📦 kho</span>.</li>
          <li>Xem thùng nào từ phiếu nào: chi tiết phiếu có khối <b>Đã nhập kho</b> link tới từng thùng;
            chi tiết thùng có mục <b>Nguồn — Phiếu nhập hàng</b>.</li>
        </ul>` },
      { title: "Trả tiền NCC từ két của mình", html: `
        <p>Trong chi tiết một phiếu nhập có khối <b>Thanh toán NCC</b>. Bấm
        <b>「Trả từ két của tôi」</b> → nhập số tiền → xác nhận. Tiền <b>trừ thẳng vào két của bạn</b>,
        phiếu ghi lại ai trả, lúc nào, từ két nào.</p>
        <ul>
          <li>Trả được <b>nhiều lần</b>. Không trả quá phần <b>còn nợ NCC</b>, không quá <b>số dư két</b>.</li>
          <li><b>Admin</b> có thể trả bằng <i>bất kỳ két nào</i> và <b>gỡ</b> một lần trả (tiền tự về lại két).</li>
          <li>Danh sách phiếu hiện chip <span class="cash-badge ok">✓ đã trả</span> hoặc
            <span class="cash-badge">nợ …</span> để biết phiếu nào còn thiếu.</li>
          <li>Không xoá được phiếu khi còn lần trả — phải <b>gỡ các lần trả</b> trước.</li>
        </ul>
        <p class="muted small">Đây là kênh tiền <b>đi ra</b> khỏi hệ két — xem thêm bài
        <a href="#/huong-dan/ket-tien">Két tiền</a>.</p>` },
      { title: "Nhà cung cấp (#/ncc)", html: `
        <p>Trang <a href="#/ncc">Nhà cung cấp</a> là danh bạ NCC: <b>tên · SĐT · địa chỉ · ghi chú</b>,
        kèm thống kê <b>số phiếu nhập · tổng tiền · lần nhập cuối</b>. Bấm một NCC để mở
        <a href="#/ncc">#/ncc/:id</a>: sửa thông tin (văn phòng), xem mọi phiếu nhập của họ,
        và <b>tạo phiếu nhập</b> ngay tại đó.</p>
        <ul>
          <li>Mỗi NCC có <b>ảnh · trao đổi · lịch sử</b> riêng.</li>
          <li><b>Xoá NCC</b> (admin) <b>bị chặn nếu NCC còn phiếu nhập</b> — phải xoá hết phiếu trước.</li>
        </ul>` },
      { title: "Mẹo & lưu ý", html: `
        <ul>
          <li>Ô tìm lọc theo <b>NCC · mã SP · ghi chú · người tạo</b> (không dấu cũng ra).</li>
          <li>Hàng nhập dùng <b>chung bảng sản phẩm</b> với bán hàng — mã hiển thị luôn là bản hiện hành.</li>
          <li>Nhập hàng <b>không tự cộng vào tồn kho thùng</b>: muốn có tồn thì tạo <b>thùng</b> trong
            <a href="#/kho">📦 Kho</a>. Phiếu nhập là để theo dõi mua/nợ tiền NCC.</li>
          <li>Danh sách tự cập nhật khi có phiếu/thanh toán mới — không cần tải lại.</li>
        </ul>` },
    ],
  },
];
