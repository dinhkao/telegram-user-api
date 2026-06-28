"""bot_core/image_crop.py — Crop whitespace from images."""
from PIL import Image


def crop_image(input_path: str, output_path: str, margin: int = 5) -> None:
    """Crop white borders from image and save."""
    image = Image.open(input_path)
    if image.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", image.size, (255, 255, 255))
        bg.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
        image = bg
    elif image.mode != "RGB":
        image = image.convert("RGB")

    white = (255, 255, 255)
    width, height = image.size
    left, top, right, bottom = 0, 0, width - 1, height - 1

    while left < width:
        col = [image.getpixel((left, y)) for y in range(height)]
        if any(p != white for p in col):
            break
        left += 1
    while right >= 0:
        col = [image.getpixel((right, y)) for y in range(height)]
        if any(p != white for p in col):
            break
        right -= 1
    while top < height:
        row = [image.getpixel((x, top)) for x in range(width)]
        if any(p != white for p in row):
            break
        top += 1
    while bottom >= 0:
        row = [image.getpixel((x, bottom)) for x in range(width)]
        if any(p != white for p in row):
            break
        bottom -= 1

    if left < right and top < bottom:
        left = max(0, left - margin)
        top = max(0, top - margin)
        right = min(width - 1, right + margin)
        bottom = min(height - 1, bottom + margin)
        image = image.crop((left, top, right + 1, bottom + 1))

    image.save(output_path, "PNG")
