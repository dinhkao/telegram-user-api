// HƯỚNG DẪN SỬ DỤNG (#/huong-dan) — danh mục bài hướng dẫn tĩnh trong app +
// bài chi tiết (#/huong-dan/:key). Bài đầu tiên: KÉT TIỀN (mọi thứ: các loại két,
// tiền chạy tự động thế nào, chuyển tiền, trả tiền nhập hàng, quyền hạn, mẹo).
// Nội dung tĩnh client-side, không gọi server. Nối: ui/Icon, nav.BackLink.
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";

export const GUIDES = [
  {
    key: "ket-tien", icon: "banknote", title: "Két tiền — ai đang giữ tiền",
    desc: "Theo dõi tiền mặt từng đơn: ai giữ, nộp chưa, khách nợ bao nhiêu, trả tiền nhập hàng.",
  },
];

export function GuidesList() {
  return (
    <div class="guide-list">
      <div class="muted small guide-intro">
        Chọn 1 bài để xem cách dùng. Có thắc mắc gì cứ hỏi Duy.
      </div>
      <AiGuideNote />
      {GUIDES.map((g) => (
        <a key={g.key} class="cash-box" href={`#/huong-dan/${g.key}`}>
          <div class="cash-box-name"><Icon name={g.icon} size={16} /> {g.title}</div>
          <div class="muted small">{g.desc}</div>
        </a>
      ))}
    </div>
  );
}

function AiGuideNote() {
  return (
    <div class="guide-ai-note">
      <Icon name="info" size={14} />
      <span>Toàn bộ hướng dẫn trong mục này được viết bởi AI, nên có thể cần Duy kiểm tra lại khi có điểm chưa rõ.</span>
    </div>
  );
}

function S({ n, title, children }: { n: number; title: string; children: any }) {
  return (
    <section class="card guide-sect">
      <h3><span class="guide-num">{n}</span> {title}</h3>
      {children}
    </section>
  );
}

export function GuideCashbox() {
  return (
    <div class="guide">
      <div class="prod-detail-head">
        <BackLink fallback="#/huong-dan" />
        <div>
          <div class="prod-sp big"><Icon name="banknote" size={17} /> Hướng dẫn: Két tiền</div>
          <div class="prod-date muted">Ai đang giữ tiền · mở từ menu ☰ Thêm → Tài chính → Két tiền</div>
        </div>
      </div>
      <AiGuideNote />

      <S n={1} title="Két tiền là gì?">
        <p>
          Trang <a href="#/ket">Két tiền</a> cho biết <b>tiền mặt của từng đơn hàng đang nằm ở đâu</b>:
          ai đang cầm, đã nộp về văn phòng chưa, khách còn nợ bao nhiêu. Mọi thứ <b>tự động</b> —
          bạn cứ làm việc như bình thường (giao hàng, nộp tiền, thu tiền), két tự cập nhật.
        </p>
        <p class="muted small">Chỉ tính các đơn tạo <b>từ ngày 14/07/2026</b> trở đi. Đơn cũ hơn không hiện ở đây.</p>
      </S>

      <S n={2} title="Có những két nào?">
        <ul>
          <li><b>Két của từng người</b> (Trí, Thảo, Trang, Duy…) — tiền mặt người đó đang cầm trong túi/ngăn kéo.</li>
          <li><b>Két văn phòng</b> — tiền mặt shipper đã nộp về, văn phòng <i>chưa</i> làm phiếu thu.</li>
          <li><b>Két ngân hàng</b> — tiền khách chuyển khoản.</li>
          <li><b>Két khách nợ</b> — tiền khách <i>còn thiếu</i> (ký toa hoặc không ký toa). Đây là tiền "trên giấy", chưa cầm được.</li>
          <li><b>Két chưa rõ</b> — đơn được đánh dấu "nộp tiền xong" nhưng <i>không chọn kết quả</i> (trả đủ hay nợ?). Cần xử lý — xem mục 7.</li>
        </ul>
      </S>

      <S n={3} title="Tiền tự chạy thế nào?">
        <p>Mỗi đơn hàng, tiền đi theo đường này:</p>
        <ol>
          <li><b>Giao hàng xong</b> → toàn bộ tiền của đơn vào <b>két người giao</b> (bạn đang cầm hộ tiền của công ty).</li>
          <li><b>Nộp tiền</b> (bấm nút Nộp tiền, chọn kết quả):
            <ul>
              <li>💵 <b>Khách trả đủ</b> → tiền chuyển sang <b>Két văn phòng</b>.</li>
              <li>📄 <b>Khách nợ</b> (có/không ký toa) → tiền chuyển sang <b>Két khách nợ</b>.</li>
              <li>🟨 <b>Chiều lấy tiền</b> → tiền <i>vẫn ở két của bạn</i> cho tới khi nộp thật.</li>
            </ul>
          </li>
          <li><b>Văn phòng thu tiền</b> (tạo phiếu thu cho đơn) → tiền chuyển vào <b>két của người tạo phiếu thu</b>.
            Nếu thu bằng <b>chuyển khoản</b> → vào <b>Két ngân hàng</b>.</li>
        </ol>
        <p class="muted small">
          Khách chuyển khoản trước khi giao? Không sao — hệ thống tự trừ, người giao chỉ "cầm" phần còn lại.
          Thu một phần cũng được: phần thu đi tiếp, phần thiếu nằm lại két khách nợ.
        </p>
      </S>

      <S n={4} title="Badge ⏰ quá hạn nộp">
        <p>
          Giao hàng xong phải <b>nộp tiền trước 17:00 cùng ngày</b> (giao sau 17:00 thì hạn là 17:00 hôm sau).
          Ai giữ tiền quá hạn sẽ có badge <span class="cash-badge">⏰ quá hạn nộp</span> ngay trên card két —
          cả văn phòng đều thấy.
        </p>
      </S>

      <S n={5} title="Chuyển tiền giữa két (văn phòng)">
        <p>
          Nút <b>Chuyển tiền</b> ở đầu trang Két tiền — dùng khi giao tiền tay: ví dụ cuối ngày Trang
          kết sổ, chuyển tiền từ <i>két Trang</i> về <i>Két văn phòng</i>. Chọn két nguồn → két đích →
          số tiền → ghi chú.
        </p>
        <ul>
          <li>Không rút quá số dư đang có của két nguồn.</li>
          <li>Chuyển nhầm? Nhờ <b>admin</b> vào timeline của két bấm <i>xoá</i> lần chuyển đó.</li>
        </ul>
      </S>

      <S n={6} title="Trả tiền nhập hàng từ két của mình">
        <p>
          Khi mua hàng của nhà cung cấp, bạn có thể trả bằng tiền đang cầm: mở <a href="#/nhap-hang">phiếu
          nhập hàng</a> → khối <b>Thanh toán NCC</b> → bấm <b>「Trả từ két của tôi」</b> → nhập số tiền.
        </p>
        <ul>
          <li>Tiền trừ thẳng vào <b>két của bạn</b>, phiếu nhập ghi lại ai trả, lúc nào, bao nhiêu.</li>
          <li>Trả nhiều lần được (trả một phần). Không trả quá số còn nợ NCC, không trả quá số dư két.</li>
          <li>Ngoài danh sách phiếu nhập sẽ thấy <span class="cash-badge ok">✓ đã trả</span> hoặc còn nợ bao nhiêu.</li>
          <li>Trả nhầm? Nhờ <b>admin</b> gỡ lần trả — tiền tự về lại két.</li>
        </ul>
      </S>

      <S n={7} title="Két chưa rõ — xử lý sao?">
        <p>
          Đơn nằm trong <b>Két chưa rõ</b> nghĩa là bước nộp tiền được tick xong mà không chọn kết quả
          (thường do tick tay từ danh sách việc). Cách sửa: mở đơn đó → bấm lại nút <b>Nộp tiền</b> →
          chọn đúng kết quả (trả đủ / nợ). Tiền sẽ tự chạy về đúng két.
        </p>
      </S>

      <S n={8} title="Ai thấy gì? (quyền hạn)">
        <ul>
          <li><b>Nhân viên</b>: chỉ thấy <i>két của mình</i> + trả tiền nhập hàng từ két của mình.</li>
          <li><b>Văn phòng</b> (Trang, Duy): thấy mọi két, tổng khách còn nợ, chuyển tiền giữa két.</li>
          <li><b>Admin</b> (Duy): thêm quyền xoá lần chuyển tiền và gỡ lần trả NCC.</li>
        </ul>
      </S>

      <S n={9} title="Mẹo xem nhanh">
        <ul>
          <li>Bấm vào 1 két → <b>timeline</b>: từng dòng tiền vào/ra, chấm tròn bên phải là <b>số dư</b> tại thời điểm đó.</li>
          <li>Trên timeline, bấm tên đơn / phiếu nhập / két đối ứng để nhảy thẳng tới đó.</li>
          <li>Đầu timeline có danh sách <b>đơn có tiền đang nằm trong két</b> — kèm giờ bắt đầu giữ.</li>
          <li>Số liệu cập nhật <b>tự động ngay</b> khi có người giao/nộp/thu — không cần bấm tải lại.</li>
        </ul>
      </S>
    </div>
  );
}
