// Chế độ "đang gõ" của tab Nhanh (CreateOrder + OrderInvoiceEdit): khi textarea
// focus → layout chia đôi màn (.co-typing, styles.css) + giấu bottom-nav. Hook
// gom 3 mảnh logic bàn phím Android WebView để 2 trang không tự chế lại:
//   1. body.co-kbd khi đang gõ (ẩn bottom-nav cho ô nhập khỏi bị đè).
//   2. BACK đóng bàn phím KHÔNG blur textarea → nghe visualViewport resize CHỈ để
//      phát hiện bàn phím đóng (viewport cao TRỞ LẠI rõ rệt) rồi blur() → layout
//      gộp lại. KHÔNG dùng viewport đo/đặt kích thước gì (chiều cao do CSS quản —
//      tránh giật). Guard: chỉ blur khi viewport đã từng THU NHỎ (hMin, lúc bàn
//      phím bật) rồi cao lại >20% + >120px — mở bàn phím / reflow không kích nhầm.
//   3. Đang gõ mà CHẠM ra ngoài textarea (vd vùng preview) → blur NGAY. Android
//      WebView đôi khi bỏ sót blur gốc → phải chạm 2 lần; gắn qua onClick (CHỈ
//      kích khi chạm, KHÔNG kích khi kéo cuộn) trên .co-split.
import { useEffect, useState } from "preact/hooks";

export function useTypingSplit(taRef: { current: HTMLTextAreaElement | null }) {
  const [typing, setTyping] = useState(false);

  useEffect(() => {
    document.body.classList.toggle("co-kbd", typing);
    return () => document.body.classList.remove("co-kbd");
  }, [typing]);

  useEffect(() => {
    if (!typing) return;
    const vv = window.visualViewport;
    if (!vv) return;
    let hMin = vv.height; // thấp nhất từng thấy trong phiên gõ này (bàn phím bật)
    const onResize = () => {
      const h = vv.height;
      if (h <= hMin) { hMin = h; return; }               // đang thu nhỏ → chỉ ghi nhớ
      if (h - hMin > 120 && h > hMin * 1.2) taRef.current?.blur(); // cao lại rõ rệt = bàn phím đóng
    };
    vv.addEventListener("resize", onResize);
    return () => vv.removeEventListener("resize", onResize);
  }, [typing]);

  const exitTypingOnOutsideTap = (e: any) => {
    const ta = taRef.current;
    if (ta && e.target !== ta) ta.blur();
  };

  return { typing, setTyping, exitTypingOnOutsideTap };
}
