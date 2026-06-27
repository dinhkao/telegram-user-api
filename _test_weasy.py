"""Test weasyprint + pdf2image HTML-to-PNG pipeline."""
from weasyprint import HTML
from pdf2image import convert_from_bytes

html_str = """<html><body style="font-family: sans-serif; padding: 20px;">
<h1>Test WeasyPrint</h1>
<p>Rendering HTML to PNG via PDF intermediate</p>
</body></html>"""

pdf_bytes = HTML(string=html_str).write_pdf()
imgs = convert_from_bytes(pdf_bytes, dpi=150)
imgs[0].save("/tmp/test_weasyprint.png", "PNG")
print(f"OK — {len(imgs)} page(s), saved to /tmp/test_weasyprint.png")
