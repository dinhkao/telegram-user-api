"""Test phần thuần của integrations/vnpt_invoice: đọc số, tính tổng, dựng XML."""
from lxml import etree

from integrations.vnpt_invoice.amount_words import amount_to_words
from integrations.vnpt_invoice.xml_build import build_invoice_xml, compute_totals


def test_amount_words_basic():
    assert amount_to_words(0) == "Không đồng"
    assert amount_to_words(5) == "Năm đồng chẵn"
    assert amount_to_words(15) == "Mười lăm đồng chẵn"
    assert amount_to_words(21) == "Hai mươi mốt đồng chẵn"
    assert amount_to_words(25) == "Hai mươi lăm đồng chẵn"
    assert amount_to_words(101) == "Một trăm lẻ một đồng chẵn"
    assert amount_to_words(390000) == "Ba trăm chín mươi nghìn đồng chẵn"


def test_amount_words_groups():
    assert amount_to_words(1_000_000) == "Một triệu đồng chẵn"
    assert (
        amount_to_words(1_234_000)
        == "Một triệu hai trăm ba mươi bốn nghìn đồng chẵn"
    )
    # nhóm giữa = 0 phải đọc "không trăm lẻ..."
    assert amount_to_words(1_005_000) == "Một triệu không trăm lẻ năm nghìn đồng chẵn"
    assert amount_to_words(2_000_000_000) == "Hai tỷ đồng chẵn"


def test_compute_totals_pre_tax():
    t = compute_totals(
        [
            {"name": "A", "unit": "bịch", "qty": 3, "price": 390000},
            {"name": "B", "unit": "hũ", "qty": 10, "price": 62000},
        ],
        8,
    )
    assert t["total"] == 3 * 390000 + 10 * 62000 == 1_790_000
    assert t["vat_amount"] == round(1_790_000 * 0.08) == 143_200
    assert t["amount"] == 1_933_200
    assert t["lines"][0]["amount"] == 1_170_000


def test_compute_totals_fractional_qty_and_kct():
    t = compute_totals([{"name": "A", "unit": "kg", "qty": 3.5, "price": 100000}], -1)
    assert t["total"] == 350000
    assert t["vat_amount"] == 0
    assert t["amount"] == 350000


def test_build_invoice_xml_shape():
    xml = build_invoice_xml(
        fkey="LTP-TEST-1",
        buyer={
            "cus_name": "Công ty A & B",
            "buyer_name": "Nguyễn Văn A",
            "tax_code": "0123456789",
            "address": "1 Lê Lợi, Q1 <TPHCM>",
            "phone": "0900000000",
            "email": "kt@congty.vn",
        },
        lines=[{"name": "Kẹo đậu phộng", "unit": "bịch", "qty": 3.5, "price": 390000}],
        vat_rate=8,
    )
    root = etree.fromstring(xml.encode("utf-8"))  # escape đúng thì parse được
    assert root.findtext(".//key") == "LTP-TEST-1"
    inv = root.find(".//Invoice")
    assert inv.findtext("CusName") == "Công ty A & B"
    assert inv.findtext("CusAddress") == "1 Lê Lợi, Q1 <TPHCM>"
    # CusCode: XSD bắt buộc CÓ MẶT nhưng luôn TRỐNG (bỏ mã khách hàng, Duy 2026-08-26)
    assert inv.find("CusCode") is not None and not (inv.findtext("CusCode") or "")
    assert inv.find("Email") is None              # XSD từ chối thẻ Email
    assert inv.findtext("EmailDeliver") == "kt@congty.vn"   # email NHẬN hoá đơn
    assert inv.findtext("VATRate") == "8"
    p = inv.find(".//Product")
    assert p.findtext("ProdQuantity") == "3.5"
    # Total per-line = cột Thành tiền trên mẫu in (thiếu là cột trống)
    assert p.findtext("Total") == p.findtext("Amount") == str(int(round(3.5 * 390000)))
    total = int(inv.findtext("Total"))
    assert int(inv.findtext("Amount")) == total + int(inv.findtext("VATAmount"))
    assert inv.findtext("AmountInWords").endswith("đồng chẵn")


def test_parse_invoice_status():
    from integrations.vnpt_invoice import parse_invoice_status
    from integrations.vnpt_invoice.core import VnptError

    # nháp còn trên VNPT, chưa phát hành (mẫu thật 2026-08-26)
    st = parse_invoice_status(
        "<Results><QRCode></QRCode><MTC></MTC><No>0</No><Pattern>1/001</Pattern><Serial>C26TTP</Serial></Results>")
    assert st == {"exists": True, "published": False, "no": 0, "mtc": ""}
    # đã phát hành: No > 0 + mã CQT
    st = parse_invoice_status(
        "<Results><QRCode>abc</QRCode><MTC>M123</MTC><No>15</No><Pattern>1/001</Pattern><Serial>C26TTP</Serial></Results>")
    assert st["exists"] and st["published"] and st["no"] == 15 and st["mtc"] == "M123"
    # không còn trên VNPT (mẫu thật)
    st = parse_invoice_status(
        "<RV><Type>0</Type><Result><MSGCODE>ERR:404</MSGCODE></Result><LastSync>20260826114013</LastSync></RV>")
    assert st == {"exists": False, "published": False, "no": 0, "mtc": ""}
    # lỗi khác → raise
    import pytest
    with pytest.raises(VnptError):
        parse_invoice_status("<RV><Result><MSGCODE>ERR:5</MSGCODE></Result></RV>")
    with pytest.raises(VnptError):
        parse_invoice_status("không phải xml")


def test_build_invoice_xml_rejects_bad_input():
    import pytest

    with pytest.raises(ValueError):
        build_invoice_xml(fkey="x", buyer={}, lines=[], vat_rate=8)
    with pytest.raises(ValueError):
        build_invoice_xml(
            fkey="x",
            buyer={},
            lines=[{"name": "A", "qty": 1, "price": 1}],
            vat_rate=7,
        )
    with pytest.raises(ValueError):
        build_invoice_xml(
            fkey="x",
            buyer={},
            lines=[{"name": " ", "qty": 1, "price": 1}],
            vat_rate=8,
        )


def test_parse_links_and_published_xml():
    import base64
    from integrations.vnpt_invoice.portal import parse_links
    from integrations.vnpt_invoice.invoices import parse_published_xml

    raw = ("<LinkInv><LinkView>https://x/view?token=a</LinkView>"
           "<LinkXML>https://x/xml?token=b</LinkXML>"
           "<LinkPDF>https://x/pdf?token=c</LinkPDF></LinkInv>")
    links = parse_links(base64.b64encode(raw.encode()).decode())
    assert links == {"view": "https://x/view?token=a", "xml": "https://x/xml?token=b",
                     "pdf": "https://x/pdf?token=c"}
    # mẫu XML TT78 thật (rút gọn) — SHDon = số hoá đơn đã cấp
    no, mtc = parse_published_xml(
        "<HDon><DLHDon><TTChung><KHHDon>C26TTP</KHHDon><SHDon>299</SHDon>"
        "<MCCQT>M1-26-ABCDE-00000000123</MCCQT></TTChung></DLHDon></HDon>")
    assert no == 299 and mtc == "M1-26-ABCDE-00000000123"
    assert parse_published_xml("<HDon></HDon>") == (0, "")
