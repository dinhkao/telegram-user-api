// Chế độ "đang gõ" của tab Nhanh (CreateOrder + OrderInvoiceEdit): khi textarea
// focus → layout chia đôi màn (.co-typing, styles.css) + giấu bottom-nav. Hook
// gom 3 mảnh logic bàn phím Android WebView để 2 trang không tự chế lại:
//   1. body.co-kbd khi đang gõ (ẩn bottom-nav cho ô nhập khỏi bị đè).
//   2. BACK đóng bàn phím KHÔNG blur textarea → nghe visualViewport resize CHỈ để
//      phát hiện bàn phím đóng (viewport về lại mốc không-bàn-phím) rồi blur() →
//      layout gộp lại. KHÔNG dùng viewport đo/đặt kích thước gì (chiều cao do CSS
//      quản — tránh giật).
//   3. Đang gõ mà CHẠM ra ngoài textarea (vd vùng preview) → blur NGAY. Android
//      WebView đôi khi bỏ sót blur gốc → phải chạm 2 lần; gắn qua onClick (CHỈ
//      kích khi chạm, KHÔNG kích khi kéo cuộn) trên .co-split.
// ⚠ Cả (2) lẫn (3) từng dùng NGƯỠNG/ĐỒNG HỒ đoán mò nên hay blur oan → "bấm vào ô
//   nhập mà không gõ được". Nay cả hai đều xét trạng thái thật, không hẹn giờ.
import { useEffect, useRef, useState } from "preact/hooks";

export function useTypingSplit(taRef: { current: HTMLTextAreaElement | null }) {
  const [typing, setTypingRaw] = useState(false);
  const baseH = useRef(0);       // chiều cao viewport lúc CHƯA có bàn phím
  const focusClick = useRef(false); // còn 1 click "đuôi" của cú chạm mở bàn phím

  // Cú chạm mở bàn phím sinh ra: pointerdown → focus → click. Click đó phát SAU
  // khi layout đã chia đôi nên rơi vào preview, không phải textarea → phải bỏ
  // qua ĐÚNG 1 click sau mỗi lần focus (xem exitTypingOnOutsideTap).
  const setTyping = (v: boolean) => {
    focusClick.current = v;   // focus → chờ 1 click đuôi; blur → không còn nợ click nào
    setTypingRaw(v);
  };

  useEffect(() => {
    document.body.classList.toggle("co-kbd", typing);
    return () => document.body.classList.remove("co-kbd");
  }, [typing]);

  useEffect(() => {
    if (!typing) return;
    const vv = window.visualViewport;
    if (!vv) return;
    // Mốc "không bàn phím" = chiều cao lúc vừa focus (bàn phím chưa kịp trượt lên);
    // focus lúc bàn phím ĐÃ mở thì mốc tự lớn dần theo lần cao nhất từng thấy.
    baseH.current = Math.max(baseH.current, vv.height);
    let hMin = vv.height;        // thấp nhất từng thấy trong phiên gõ này
    const onResize = () => {
      const h = vv.height;
      if (h > baseH.current) baseH.current = h;
      if (h <= hMin) { hMin = h; return; }
      // Bàn phím ĐÓNG = viewport trở lại (gần) đúng mốc không-bàn-phím. Ngưỡng
      // TƯƠNG ĐỐI cũ (cao lên >120px & >20%) bắn nhầm mỗi khi bàn phím chỉ ĐỔI CỠ
      // — đóng bảng emoji/clipboard, đổi bàn phím, IME bật/tắt hàng gợi ý — làm ô
      // nhập tự mất focus giữa chừng.
      if (h >= baseH.current - 40) taRef.current?.blur();
    };
    vv.addEventListener("resize", onResize);
    return () => vv.removeEventListener("resize", onResize);
  }, [typing]);

  const exitTypingOnOutsideTap = (e: any) => {
    const ta = taRef.current;
    if (!ta || e.target === ta) return;
    // 1) Click đuôi của chính cú chạm vừa focus → bỏ qua (điểm chạm giờ nằm trên
    //    preview vì layout đã chia đôi). Trước đây bỏ qua theo ĐỒNG HỒ (400ms sau
    //    khi bắt đầu gõ) — click đến muộn hơn thế mỗi khi main thread kẹt (reflow
    //    chia đôi + preview render + bàn phím trượt) thì guard hết hạn → blur oan.
    if (focusClick.current) { focusClick.current = false; return; }
    // 2) Chạm nằm TRONG khung ô nhập hiện tại (viền/padding, hoặc lệch vài px do
    //    layout vừa đổi) → không bao giờ blur.
    const x = e.clientX, y = e.clientY;
    if (typeof x === "number" && typeof y === "number" && (x || y)) {
      const r = ta.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return;
    }
    ta.blur();
  };

  return { typing, setTyping, exitTypingOnOutsideTap };
}
