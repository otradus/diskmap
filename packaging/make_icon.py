"""Draw packaging/icon.png (1024x1024): the diskmap logo, three treemap tiles.

Run with Pillow installed:  python packaging/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024
OUT = Path(__file__).with_name("icon.png")

# Same hues as the app's Documents & media / Code projects / Package caches tiles, a bit stronger.
ORANGE, PURPLE, BLUE = (240, 152, 101), (139, 127, 236), (113, 147, 232)


def main() -> None:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Soft shadow, then the rounded "squircle" base inside Apple's 824px icon grid.
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((100, 112, 924, 936), 185, fill=(0, 0, 0, 70))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((100, 100, 924, 924), 185, fill=(250, 250, 251), outline=(226, 226, 230), width=4)

    pad, gap, r = 205, 34, 54
    left, top, right, bottom = pad, pad, S - pad, S - pad
    split_x = left + int((right - left) * 0.56)
    split_y = top + int((bottom - top) * 0.52)
    d.rounded_rectangle((left, top, split_x - gap // 2, bottom), r, fill=ORANGE)
    d.rounded_rectangle((split_x + gap // 2, top, right, split_y - gap // 2), r, fill=PURPLE)
    d.rounded_rectangle((split_x + gap // 2, split_y + gap // 2, right, bottom), r, fill=BLUE)

    img.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
